import boto3
import json
import os
import uuid

ssm = boto3.client("ssm")
runtime = boto3.client("bedrock-agent-runtime")

# Fetch and cache IDs
AGENT_ID = ssm.get_parameter(Name=os.environ["BEDROCK_AGENT_ID_PARAM"])["Parameter"]["Value"]
ALIAS_ID = ssm.get_parameter(Name=os.environ["BEDROCK_AGENT_ALIAS_ID_PARAM"])["Parameter"]["Value"]

def handler(event, context):
    body = json.loads(event.get("body", "{}"))
    message = body.get("message")
    session_id = body.get("session_id", str(uuid.uuid4()))

    if not message:
        return respond(400, {"error": "Missing 'message'"})

    response = runtime.invoke_agent(
        agentId=AGENT_ID,
        agentAliasId=ALIAS_ID,
        sessionId=session_id,
        input={"text": message}
    )

    return respond(200, {
        "response": response["completion"]["content"],
        "session_id": session_id
    })

def respond(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body)
    }
    
    