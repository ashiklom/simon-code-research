from lib import client, result

TITLE = "EC2 instance (AL2023 AMI from SSM public parameter, user_data)"
CATEGORY = "Containers & VMs"
AWS_EXPECTED = "Instance boots; console output shows user_data ran."
FINDINGS = ["no-container-or-vm-execution", "ec2-runinstances-empty-az"]


def check(outputs, row):
    ec2 = client("ec2")
    noaz = None
    if outputs.get("noaz_subnet"):
        noaz = ec2.describe_subnets(SubnetIds=[outputs["noaz_subnet"]])["Subnets"][0].get("AvailabilityZone")
    if not row["apply"]["ok"]:
        return result("gap", f"{row['apply']['error']} | subnet created without availability_zone has AZ={noaz!r}")
    st = ec2.describe_instances(InstanceIds=[outputs["id"]])["Reservations"][0]["Instances"][0]["State"]["Name"]
    try:
        out = ec2.get_console_output(InstanceId=outputs["id"]).get("Output")
    except Exception as e:  # noqa: BLE001
        out = f"error {e}"[:100]
    ran = bool(out) and "probe-userdata-ran" in str(out)
    return result("works" if ran else "partial", f"ami={outputs.get('ami')} state={st} console_output={str(out)[:80]!r}; "
                  f"subnet created without availability_zone has AZ={noaz!r}. Without availability_zone on the instance, the "
                  "provider sends Placement.AvailabilityZone='' which the emulator rejects (AWS ignores it).")
