#!/usr/bin/env python3
import os
from aws_cdk import App, Environment

from agent_stack import AgentStack

app = App()

env = Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"),
    region=os.getenv("CDK_DEFAULT_REGION"),
)

AgentStack(app, "AgentStack", env=env)

app.synth()
