from lib import client, result

TITLE = "aws_security_group in a new VPC"
CATEGORY = "OpenTofu provider x emulator"
AWS_EXPECTED = "AWS adds a default allow-all egress rule to every new SG; the provider revokes it, then adds the configured rules."
FINDINGS = ["ec2-sg-default-egress"]
EXPECT_APPLY_FAILURE = True


def check(outputs, row):
    if row["apply"]["ok"]:
        return result("works", "security group applied")
    sgs = client("ec2").describe_security_groups(Filters=[{"Name": "group-name", "Values": ["probe-sg"]}])["SecurityGroups"]
    egress = sgs[0]["IpPermissionsEgress"] if sgs else None
    return result("gap", f"{row['apply']['error'][:250]} | new SG egress rules as created by the emulator: {egress}")
