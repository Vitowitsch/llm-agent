from aws_cdk import (
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_apigateway as apigw,
    aws_s3 as s3,
    aws_secretsmanager as secretsmanager,
    aws_s3_deployment as s3deploy,
    Stack, Duration
)
from constructs import Construct

class AgentStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        bucket = s3.Bucket(self, "FaqBucket", bucket_name="faq-443370675100")
        s3deploy.BucketDeployment(
            self,
            "DeployCSV",
            destination_bucket=bucket,
            sources=[s3deploy.Source.asset("./assets")],
            destination_key_prefix="",
        )
        
        # pinecone_secret = secretsmanager.Secret.from_secret_complete_arn(
        #     self,
        #     "ImportedPineConeSecret",
        #     "arn:aws:secretsmanager:eu-central-1:944997240237:secret:pinecone-KUcwu2",
        # )

        pinecone_secret = secretsmanager.Secret(
            self, "pinecone",
            secret_name="pinecone-api-key"
        )

        lambda_role = iam.Role(
            self, "BedrockLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ]
        )

        pinecone_secret.grant_read(lambda_role)
        bucket.grant_read(lambda_role)

        provision_lambda = _lambda.Function(
            self, "ProvisionAgentLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="provision.handler",
            code=_lambda.Code.from_asset("lambda/provision"),
            role=lambda_role,
            environment={
                "S3_BUCKET": bucket.bucket_name,
                "PINECONE_SECRET_NAME": pinecone_secret.secret_name
            },
            timeout=Duration.minutes(3)
        )

        invoke_lambda = _lambda.Function(
            self, "InvokeAgentLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="invoke.handler",
            code=_lambda.Code.from_asset("lambda/invoke"),
            role=lambda_role,
            environment={
                "BEDROCK_AGENT_ID_PARAM": "/bedrock/agent/id",
                "BEDROCK_AGENT_ALIAS_ID_PARAM": "/bedrock/agent/alias"
            },
            timeout=Duration.minutes(3)
        )

        apigw.LambdaRestApi(
            self, "AgentInvokeAPI",
            handler=invoke_lambda
        )