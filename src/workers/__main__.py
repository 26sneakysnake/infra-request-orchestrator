"""Run the job workers and the ServiceNow poller: python -m workers

NETCO_POLL_ONLY=RITM0010007,RITM0010008 restricts the poller to these requests (used by the e2e
scenario, so it never picks up other open requests).
"""

import asyncio
import logging
import os
import sys
import threading
from collections.abc import Callable
from typing import Any

import camunda_orchestration_sdk as sdk
import loguru
from camunda_orchestration_sdk import JobError, JobFailure, SyncJobContext, WorkerConfig

from integrations.config import JiraSettings, ServiceNowSettings
from integrations.jira import JiraClient
from integrations.servicenow import ServiceNowClient
from k8s.cluster import Cluster
from scenario.camunda import camunda_async_client, camunda_client
from workers.handlers import HANDLERS, Deps, Variables
from workers.poller import poll_forever

log = logging.getLogger("workers")
PROCESS_ID = "expose_service"
REPLY_MESSAGE = "requester-reply"
RETRY_BACK_OFF_MS = 10_000
# How long a job stays reserved by a worker. Kept short: if a worker dies, its jobs come back after
# this delay. The verification may wait up to 2 min for the deployment, hence its longer timeout.
JOB_TIMEOUT_MS = {"verify-exposure": 180_000}
DEFAULT_JOB_TIMEOUT_MS = 60_000


def build_deps() -> Deps:
    sn = ServiceNowSettings.from_env()
    jira = JiraSettings.from_env()
    return Deps(
        servicenow=ServiceNowClient(sn.instance_url, sn.username, sn.password),
        jira=JiraClient(jira.base_url, jira.email, jira.api_token),
        jira_project=jira.project_key,
        cluster=Cluster(os.environ.get("KUBE_CONTEXT", "kind-netco")),
    )


def adapt(
    handler: Callable[[Variables, Deps], Variables], deps: Deps
) -> Callable[[SyncJobContext], Variables]:
    def callback(job: SyncJobContext) -> Variables:
        try:
            return handler(job.variables.to_dict(), deps)
        except JobError:
            raise
        except Exception as exc:
            # Technical failure: retry after a pause; Operate shows an incident once out of retries.
            log.exception("Job %s failed", job.type_)
            raise JobFailure(
                message=f"{type(exc).__name__}: {exc}", retry_back_off=RETRY_BACK_OFF_MS
            ) from exc

    return callback


def start_instance(variables: dict[str, Any], business_id: str) -> str:
    result = camunda_client().create_process_instance(
        data=sdk.ProcessCreationById(
            process_definition_id=PROCESS_ID,
            variables=sdk.ProcessInstanceCreationInstructionByIdVariables.from_dict(variables),
            business_id=business_id,
        )
    )
    return str(result.process_instance_key)


def correlate_reply(request_number: str, reply: str) -> None:
    """Hand the requester's reply to the instance waiting for it (fails if none is waiting yet)."""
    camunda_client().correlate_message(
        data=sdk.MessageCorrelationRequest(
            name=REPLY_MESSAGE,
            correlation_key=request_number,
            variables=sdk.MessageCorrelationRequestVariables.from_dict({"reply": reply}),
        )
    )


async def run() -> None:
    deps = build_deps()
    only = [n.strip() for n in os.environ.get("NETCO_POLL_ONLY", "").split(",") if n.strip()]
    stop = threading.Event()
    async with camunda_async_client() as client:
        for job_type, handler in HANDLERS.items():
            client.create_job_worker(
                config=WorkerConfig(
                    job_type=job_type,
                    job_timeout_milliseconds=JOB_TIMEOUT_MS.get(job_type, DEFAULT_JOB_TIMEOUT_MS),
                    request_timeout_milliseconds=20_000,  # long polling
                    max_concurrent_jobs=2,
                    worker_name="netco-workers",
                ),
                callback=adapt(handler, deps),
                execution_strategy="thread",
            )
        poller = asyncio.create_task(
            asyncio.to_thread(
                poll_forever, deps.servicenow, start_instance, correlate_reply, stop, only or None
            )
        )
        log.info("Workers started for %s", ", ".join(HANDLERS))
        try:
            await client.run_workers()
        finally:
            stop.set()
            await poller


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    # The SDK logs through loguru, whose default sink prints everything down to DEBUG.
    loguru.logger.remove()
    loguru.logger.add(sys.stderr, level="WARNING")
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log.info("Stopped")


if __name__ == "__main__":
    main()
