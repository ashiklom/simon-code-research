# simon-code-research
Code research projects, inspired by Simon Willison

- [aws-emulator-tofu](aws-emulator-tofu/): an OpenTofu-deployed CloudFront → API Gateway → Lambda stack with Cognito-JWT roles (titiler/tipg-style backends, S3, Aurora) run entirely on AWS's aws-emulator, plus probes of what the emulator can and can't do versus real AWS. ([site](https://ashiklom.github.io/simon-code-research/aws-emulator-tofu/))
- [l2-swath-geolocation](l2-swath-geolocation/): locating pixels (KD-tree, S2, H3, xoak, analytic orbit geometry), true pixel footprints/PSFs and their effect on areal means, and network read performance (incl. virtual Zarr) for MODIS, VIIRS and ECOSTRESS L2 swaths. ([site](https://ashiklom.github.io/simon-code-research/l2-swath-geolocation/))
