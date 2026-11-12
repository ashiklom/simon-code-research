import json

from lib import client, result

TITLE = "KMS key + alias, Secrets Manager secret encrypted with it"
CATEGORY = "Security services"
AWS_EXPECTED = "Encrypt/Decrypt round-trip via alias; GetSecretValue returns the stored JSON; rotation flag on key."
FINDINGS = []


def check(outputs, row):
    kms = client("kms")
    ct = kms.encrypt(KeyId="alias/probe", Plaintext=b"hello-kms")["CiphertextBlob"]
    pt = kms.decrypt(CiphertextBlob=ct)["Plaintext"]
    sv = json.loads(client("secretsmanager").get_secret_value(SecretId=outputs["secret"])["SecretString"])
    rot = kms.get_key_rotation_status(KeyId=outputs["key"])["KeyRotationEnabled"]
    ok = pt == b"hello-kms" and sv == {"user": "u", "password": "p"} and rot
    return result("works" if ok else "gap", f"decrypt_ok={pt == b'hello-kms'} secret_ok={sv == {'user': 'u', 'password': 'p'}} rotation={rot}")
