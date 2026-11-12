from lib import client, result, wait_for

TITLE = "ECS Fargate RunTask (busybox container)"
CATEGORY = "Containers & VMs"
AWS_EXPECTED = "Task goes PROVISIONING -> RUNNING -> STOPPED with container exit code 0."
FINDINGS = ["no-container-or-vm-execution"]


def check(outputs, row):
    ecs = client("ecs")
    t = ecs.run_task(cluster=outputs["cluster"], taskDefinition=outputs["taskdef"], launchType="FARGATE",
                     networkConfiguration={"awsvpcConfiguration": {"subnets": [outputs["subnet"]],
                                                                     "assignPublicIp": "ENABLED"}})
    if not t.get("tasks"):
        return result("gap", f"RunTask failures: {t.get('failures')}")
    arn = t["tasks"][0]["taskArn"]
    seen = []

    def stopped():
        d = ecs.describe_tasks(cluster=outputs["cluster"], tasks=[arn])["tasks"][0]
        seen.append(d["lastStatus"])
        return d if d["lastStatus"] == "STOPPED" else None
    d = wait_for(stopped, timeout=90, every=2)
    statuses = list(dict.fromkeys(seen))
    if d:
        ec = [c.get("exitCode") for c in d.get("containers", [])]
        return result("partial", f"status sequence {statuses}, exit codes {ec}, stopCode={d.get('stopCode')!r}, "
                                 f"stopReason={d.get('stoppedReason')!r}. The lifecycle (incl. a modelled image-pull "
                                 "reachability check against the VPC's routes) is simulated; the container command never runs.")
    return result("partial", f"status sequence {statuses} (never STOPPED within 90 s); the container command "
                             "(echo probe-ecs-ran; sleep 2) would have exited after ~2 s on AWS")
