from lib import client, result

TITLE = "EC2 instance (AL2023 AMI from SSM public parameter, user_data)"
CATEGORY = "Containers & VMs"
AWS_EXPECTED = "Instance boots; console output shows user_data ran."
FINDINGS = ["no-container-or-vm-execution"]


def check(outputs, row):
    if not row["apply"]["ok"]:
        return result("gap", row["apply"]["error"])
    ec2 = client("ec2")
    st = ec2.describe_instances(InstanceIds=[outputs["id"]])["Reservations"][0]["Instances"][0]["State"]["Name"]
    try:
        out = ec2.get_console_output(InstanceId=outputs["id"]).get("Output")
    except Exception as e:  # noqa: BLE001
        out = f"error {e}"[:100]
    ran = bool(out) and "probe-userdata-ran" in str(out)
    return result("works" if ran else "partial", f"ami={outputs.get('ami')} state={st} console_output={str(out)[:80]!r}")
