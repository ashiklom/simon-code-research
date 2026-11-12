# Prompts

## Prompt

https://github.com/aws/aws-emulator

New experiment: aws-emulator-tofu. Create a Terraform stack using opentofu that exclusively uses the AWS emulator. Create an API --- API Gateway through cloudfront that talks to a Lambda --- that reads data from an S3 bucket: Use a basic titiler deployment with some small public COGs as the example. Add an RDS Aurora database in there too, with an API in front of it: Use tipg for this with some small public vector data, so tipg provides OGC API Features. Also create a Cognito user pool with a service that mints user-specific JWTs for each user. Each user can have tiler permissions , tipg permissions, or "admin" (all current and future API permissions). Authenticate the tiler and tipg APIs using the JWTs according to the user roles.

Two overarching goals here: (1) Demonstrate a good design for the authenticated API pattern with different users having different roles. (2) Test the ability of aws-emulator to emulate different AWS services and the ability of opentofu to deploy to these services. The report website should have a single high level summary landing page that links to dedicated pages for each of these goals: how the authenticated API works and is deployed, and how well OpenTofu + aws-emulator worked.

Once done the core objectives, keep probing the capabilities of opentofu + aws-emulator to figure out what (if anything) aws-emulator can't do that AWS can (within reason).

## Claude: question

> Research blocker: aws-emulator runs Lambda Python on an embedded RustPython interpreter. It can't load C extensions (numpy, GDAL, pydantic-core), open sockets (asyncpg), or run container-image Lambdas. Its Aurora PostgreSQL is SQLite behind a Postgres wire front with no PostGIS. So real titiler and tipg cannot run inside the emulator. How should I handle the tiler/features backends?

Options:

1. **Stand-ins + real probe (Recommended)**: Write small pure-Python 'titiler-lite' and 'tipg-lite' Lambdas with titiler/tipg-compatible URLs. They read COGs from S3 by range request and features via the RDS Data API, so the whole authenticated stack runs end-to-end in the emulator. Also deploy a real titiler/tipg (container image + Aurora PostGIS) variant as a probe and document exactly where it breaks.
2. **Real titiler/tipg, deploy-only**: Write the stack for real AWS: titiler and tipg as container-image Lambdas plus Aurora with PostGIS. Test only that OpenTofu can apply and destroy it on the emulator. No live API requests succeed, so the auth design is shown in code but not exercised.
3. **Real apps in local Docker**: Run real titiler, tipg and PostGIS as Docker containers outside the emulator. Use the emulator only for Cognito, S3 and the control plane. API Gateway and CloudFront can't route to them, so JWT checks would live in middleware, not in API Gateway.

## Answer

Stand-ins + real probe (Recommended)

## Plan review comments (first round)

On the plan text "constraints that shape the plan:"

> All of these constraints, and any additional constraints/behavior differences of aws-emulator vs. real AWS, should be clearly reported on the website in a dedicated section on differences between aws-emulator vs. real AWS.
>
> For all of the constraints below, clarify which ones are specific to aws-emulator vs. which ones would also be problems in real AWS (e.g., is the HTTP API v2 JWT no signature verification just in aws-emulator, or a general HTTP limitation? What about Cloudfront not forwarding Authorization and dropping origin — all cloudfront, or just the aws-emulator version?).

On the plan text "Lambda. Handlers run in-process on RustPython (Python) or QuickJS (Node). There are no C extensions, no sockets, no container-image Lambdas and no Python layers."

> This is a major limitation. Make sure this is clealy and loudly documented in the final report.

On the plan text "Provider configuration."

> Save these instructions in an agent-friendly markdown file somewhere, so that I can point future AI agents prototyping AWS capabilities using tofu + aws-emulator at this and save them some time.

On the plan text "tiler-lite tiles must be pixel-identical to rio-tiler reading the same COG."

> Too strict --- this can be relaxed since this is just a proof-of-concept. The only thing that has to agree is the API shape/surface for the most common cases: Same request parameters, same response (again, **most common use case**; don't need to support edge cases).

## Plan review comments (second round)

> Somewhere, add an UPDATE.md (or similar) that gives agent-friendly instructions for updating the findings as aws-emulator is developed. First check is to see if aws-emulator itself was updated at all, and if so, how. If the changes do not address any of the functionality/limitations you found, just update the date of the last check and end. If the changes do resolve some of the issues, check anything that might be affected and update your findings accordingly.
>
> This also means that you should record and report the .deb version, associated commit hash on the aws-emualor GitHub, and the timestamp of the check.
>
> The update step should run against the latest .Deb release by default, but optionally have the ability to build a .Deb of the source if the user requests.
