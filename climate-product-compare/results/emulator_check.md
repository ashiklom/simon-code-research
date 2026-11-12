# Remote store backends against AWS Emulator

AWS Emulator 1.0.322 (Debian package, signature verified), telemetry off. Scripts:
`scripts/emulator_check.py` (signature-auth emulator, S3 + CloudFront) and
`scripts/emulator_http_noauth.py` (second emulator with `--auth off`, public bucket over
HTTPS). Raw numbers: `results/emulator_check.json`.

**Test data.** Subsets of four repos were built from the local store, and every value in each
subset was compared after the round trip:

| Repo | Contents |
|---|---|
| CHIRPS v3 | 3 sites × 2 years, daily |
| ERA5-Land | 3 sites × 2 years, hourly, 18 vars |
| HRRR | 2 sites × 1 year, hourly, 10 vars |
| USCRN obs | 3 sites × 2 years, hourly, 20 vars |

In total that is about 5.5 M values and 6 MB of Icechunk objects.

## Summary

| Path | Result |
|---|---|
| `s3://` backend (write with `store-copy`, read back) | **Works.** 215 objects / 6 MB copied in 2.6–4.5 s. Every repo read back bit-identical (max \|diff\| = 0) in 0.1–0.6 s. Signed range GETs return `206`. |
| CloudFront distribution in front of the private bucket (Origin Access Control) | **Control plane works; data plane only partly.** `CreateOriginAccessControl` and `CreateDistribution` succeed, and the emulator serves the distribution on a local port (`127.0.0.1:<port>`). Whole-object GETs return `200` with `x-cache: Miss`, then `Hit`, and direct anonymous S3 GETs are correctly denied (`403`). But the emulated distribution **ignores HTTP `Range` headers**: it returns `200` with the full body instead of `206`. Icechunk's HTTP storage (Rust `object_store`) rejects that ("Range request not supported"), so **Icechunk reads through the emulated CloudFront fail**. Real CloudFront supports byte-range GETs from S3 origins, so this is an emulator gap, not a design problem. |
| `https://` backend straight from a public-read bucket (no CloudFront), auth-off emulator | **Works.** All four repos read bit-identical in 0.2–0.8 s over anonymous range GETs (`206`). This exercises exactly the path CloudFront would serve: anonymous HTTPS with byte ranges, read-only. |

## Details and caveats

- **Public access.**
  - New buckets, and the account, block public policies by default, as on AWS.
  - With the default signature-auth emulator, deleting the bucket's public-access block and
    adding a `Principal: "*"` read policy is accepted (`GetBucketPolicyStatus` →
    `IsPublic: true`). Anonymous GETs are still refused (`403`), apparently because that mode
    rejects every unsigned request.
  - With `--auth off`, the same policy makes anonymous reads work.
  - The account-level `s3control` endpoint could not be reached: boto3 builds
    `<account>.127.0.0.1` host names. Deleting the bucket-level block was enough.
- **TLS and credentials.**
  - The emulator serves HTTPS with its own CA (`~/.aws/emulator/<port>/ca.pem`). Icechunk
    (Rust) and boto3 both trusted it once a combined bundle was exported in `SSL_CERT_FILE` /
    `AWS_CA_BUNDLE`.
  - The `s3://` root needs `?endpoint=https://127.0.0.1:9297&force_path_style=1`.
  - Credentials come from the emulator's per-run key file, exported as `AWS_*`
    (`from_env`). Real AWS session tokens in the environment were unset first.
- **What this validates for a future real deployment.**
  - The store layout copies unchanged to S3 (`mise run store-copy -- file://… s3://bucket/prefix`).
  - Readers can switch to `s3://…` or `https://<cloudfront-domain>/prefix` without code
    changes.
  - The HTTPS reader works as long as the origin honours byte ranges, which real CloudFront
    does.
  - The remaining unverified piece is Icechunk-through-CloudFront end to end. Check it once
    against a real distribution, with OAC and the bucket policy shown in the script.
