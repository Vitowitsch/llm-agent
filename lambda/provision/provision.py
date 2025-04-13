# lambda/provision/provision.py
import boto3
import os
import json
import pinecone
import time

bedrock = boto3.client("bedrock-agent")
ssm = boto3.client("ssm")
secrets = boto3.client("secretsmanager")


def handler(event, context):
    try:
        config = load_pinecone_config()
        ensure_index(config)
        kb_id = create_kb(config)
        poll_kb_ready(kb_id)
        agent_id, alias_id = create_agent(kb_id)
        save_to_ssm(agent_id, alias_id)
        return respond(200, {
            "agent_id": agent_id,
            "alias_id": alias_id,
            "kb_id": kb_id,
            "pinecone_index": config["index"]
        })
    except Exception as e:
        return respond(500, {"error": str(e)})


def load_pinecone_config():
    secret_name = os.environ["PINECONE_SECRET_NAME"]
    secret = secrets.get_secret_value(SecretId=secret_name)
    data = json.loads(secret["SecretString"])
    env = data.get("PINECONE_ENVIRONMENT", "eu-central-aws")
    if not env.endswith("-aws"):
        raise ValueError(f"Invalid Pinecone env: {env}")
    return {
        "api_key": data["PINECONE_API_KEY"],
        "env": env,
        "index": data.get("PINECONE_INDEX", "faq-index"),
        "secret_arn": secret["ARN"]
    }


def ensure_index(cfg):
    pinecone.init(api_key=cfg["api_key"], environment=cfg["env"])
    if cfg["index"] not in pinecone.list_indexes():
        pinecone.create_index(
            name=cfg["index"],
            dimension=1536,
            metric="cosine",
            metadata_config={"indexed": ["question", "answer"]}
        )


def create_kb(cfg):
    bucket = os.environ["S3_BUCKET"]
    kb = bedrock.create_knowledge_base(
        name="faq-kb",
        knowledgeBaseConfiguration={
            "type": "VECTOR",
            "vectorKnowledgeBaseConfiguration": {
                "embeddingModelArn": "arn:aws:bedrock:eu-central-1::foundation-model/amazon.titan-embed-text-v1"
            }
        },
        dataSourceConfiguration={
            "s3": {
                "bucketArn": f"arn:aws:s3:::{bucket}",
                "inclusionPrefixes": ["faq.csv", "docs/"]
            }
        },
        storageConfiguration={
            "pinecone": {
                "connectionString": f"https://controller.{cfg['env']}.pinecone.io",
                "credentialsSecretArn": cfg["secret_arn"],
                "indexName": cfg["index"]
            }
        }
    )
    return kb["knowledgeBase"]["knowledgeBaseId"]


def create_agent(kb_id):
    agent = bedrock.create_agent(
        name="faq-agent",
        instruction="You are a helpful assistant for customer FAQ.",
        foundationModel="anthropic.claude-v2",
        knowledgeBaseIds=[kb_id],
        agentResourceRoleArn="arn:aws:iam::<your-account-id>:role/AgentExecutionRole"
    )
    alias = bedrock.create_agent_alias(agentId=agent["agent"]["agentId"], aliasName="default")
    return agent["agent"]["agentId"], alias["agentAlias"]["agentAliasId"]


def save_to_ssm(agent_id, alias_id):
    ssm.put_parameter(Name="/bedrock/agent/id", Value=agent_id, Type="String", Overwrite=True)
    ssm.put_parameter(Name="/bedrock/agent/alias", Value=alias_id, Type="String", Overwrite=True)


def respond(code, body):
    return {
        "statusCode": code,
        "body": json.dumps(body),
        "headers": {"Content-Type": "application/json"}
    }



def poll_kb_ready(kb_id, timeout_seconds=120):
    start = time.time()
    while True:
        status = bedrock.get_knowledge_base(knowledgeBaseId=kb_id)["knowledgeBase"]["status"]
        print(f"[STATUS] Knowledge base {kb_id} is {status}")
        if status == "ACTIVE":
            return
        elif status == "FAILED":
            raise Exception(f"Knowledge base creation failed: {kb_id}")
        elif time.time() - start > timeout_seconds:
            raise TimeoutError("Timed out waiting for KB to become ACTIVE")
        time.sleep(5)
        
        