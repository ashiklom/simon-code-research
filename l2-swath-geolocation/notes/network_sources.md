# Network-profile sources (research notes, compiled by a research sub-agent)
[C] cited, [A] assumed/derived, [M] measured by the sub-agent with curl from a US-East vantage through a TLS-intercepting proxy (indicative only).

## Key findings
- NASA Earthdata Cloud S3 buckets are only readable from us-west-2 (s3credentials STS policy) [C] -> "S3 out-of-region" is a what-if for NASA data.
- TEA (Thin Egress App) answers every authenticated GET with 303 to a fresh pre-signed S3 URL (<=3600 s, Cache-Control private max-age~3540) and does an S3 HeadObject per request [C: TEA app.py]. fsspec/aiohttp follow it on every range request (no redirect cache) [C]; GDAL caches the signed target (CPL_VSIL_CURL_USE_S3_REDIRECT) [C] -> HTTPS only ~4% slower than in-region S3 in a GDAL benchmark (8.08 vs 7.74 s) [C: Rodman 2023].
- First access with no cookie: ~5-6 HTTP exchanges over 3 hosts (CloudFront/Lambda 302 -> URS -> TEA /login -> 301 -> 303 -> S3) [C/A]; Bearer token skips URS steps.
- TEA Lambda 302 median 245 ms vs plain S3 GET 125 ms from same vantage [M] -> ~120+ ms per TEA hop.

## S3 in-region
- <512 KB requests: "median latencies often in the tens of milliseconds"; retry after 2 s [C AWS]. 100-200 ms is AWS's "consistent latency" statement, not the median [C].
- Durner et al. 2023 (VLDB): base ~30 ms + ~20 ms/MiB; <5% first byte >200 ms; per-request 25-95 MiB/s, median 55-60, ceiling ~95 MiB/s; some requests get lost [C]. dvassallo: p90 TTFB ~20 ms, ~93 MB/s/thread [C]. AWS: 85-90 MB/s per connection, 8-16 MB ranges [C].
- >= 5,500 GET/HEAD/s per prefix; 503 SlowDown only while rescaling [C]. EC2 internet-gateway 5 Gbps for <32 vCPU [C].

## S3 out-of-region
- us-east-1 -> us-west-2 RTT ~71 ms [C]; TCP+TLS1.3 2 RTT ~140 ms, TLS1.2 ~210 ms [A]. Warm 16 KB GETs to us-west-2 median 130 ms, p90 153 ms [M]. EC2 us-east-1 2x slower, laptop ~7x slower than in-region [C: Rodman].

## NCCS datashare
- Almost nothing published. nginx/1.14.1, HTTP/1.1 only, Accept-Ranges, ETag, no auth/redirect/CDN [M]. 16 KB TTFB median 103 ms (67-126) [M]; single connection 20 MB/s; aggregate 6/17/22/35 MB/s at 1/4/8/16 parallel 4 MB GETs [M]. OPeNDAP sibling showed a funding-lapse notice (Oct 2025) [C]. Per-IP cap by analogy with NCAR RDA (10 streams) [C].

## Reader request patterns
- HDF5 lib metadata in ~4 KB pieces, one read per chunk; paged aggregation helps; 10x bigger chunks ~10x faster [C: Lopez et al.]. HDF5 1.14 ROS3 caches first 16 MiB; HDF5 2.0 64 MiB page buffer [C].
- fsspec DEFAULT_BLOCK_SIZE 5 MiB, HTTP default cache "bytes"; s3fs default_block_size 50 MiB readahead, 5 retries [C]. earthaccess.open: cache_type "background", 4/8/16 MiB blocks by file size [C].
- GDAL /vsicurl/: 16 KB chunks growing to 2 MB on sequential reads; 16 MB LRU; GDAL_HTTP_MAX_RETRY=0 by default [C].
- kerchunk/VirtualiZarr: one GET per chunk, no coalescing [A]; non-inlined small coords made open 4-6 min [C: VirtualiZarr #511].

## Bibliography
- AWS S3 performance guidelines: https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html
- AWS whitepaper "Best Practices Design Patterns: Optimizing Amazon S3 Performance" (2019)
- EC2 bandwidth: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-network-bandwidth.html
- Durner, Leis, Neumann (2023) Exploiting Cloud Object Storage for High-Performance Analytics. PVLDB 16(11). https://vldb.org/pvldb/vol16/p2769-durner.pdf
- dvassallo/s3-benchmark: https://github.com/dvassallo/s3-benchmark
- TEA: https://github.com/asfadmin/thin-egress-app ; https://tea-docs.asf.alaska.edu/configuration
- Earthdata forum (out-of-region 403): https://forum.earthdata.nasa.gov/viewtopic.php?p=16180
- Rodman (2023) NASA S3 compute location test: https://hrodmn.dev/posts/nasa-s3/
- Lopez et al. Evaluating Cloud-Optimized HDF5 for ICESat-2: https://nsidc.github.io/cloud-optimized-icesat2/paper.pdf
- Cloud-Optimized HDF/NetCDF guide: https://guide.cloudnativegeo.org/cloud-optimized-netcdf4-hdf5/
- GDAL config options: https://gdal.org/en/stable/user/configoptions.html ; /vsicurl/: https://gdal.org/en/stable/user/virtual_file_systems.html
- VirtualiZarr #511: https://github.com/zarr-developers/VirtualiZarr/issues/511
- NCCS: https://www.nccs.nasa.gov/?p=4027 ; NCAR RDA limits: https://rda.ucar.edu/support/faqs/problems-encountered-when-downloading-data
