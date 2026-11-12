"""Push a minimal OCI image (one tiny layer) to an ECR repository using only the ECR API."""
import gzip
import hashlib
import io
import json
import sys
import tarfile

import boto3

repo = sys.argv[1]
ecr = boto3.client("ecr")

tar_buf = io.BytesIO()
with tarfile.open(fileobj=tar_buf, mode="w") as t:
    data = b"def handler(event, context):\n    return {'statusCode': 200, 'body': 'titiler stand-in'}\n"
    info = tarfile.TarInfo("var/task/handler.py")
    info.size = len(data)
    t.addfile(info, io.BytesIO(data))
tar = tar_buf.getvalue()
layer = gzip.compress(tar)
config = json.dumps({"architecture": "amd64", "os": "linux",
                     "config": {"Cmd": ["handler.handler"], "WorkingDir": "/var/task"},
                     "rootfs": {"type": "layers", "diff_ids": ["sha256:" + hashlib.sha256(tar).hexdigest()]}}).encode()


def upload(blob):
    digest = "sha256:" + hashlib.sha256(blob).hexdigest()
    up = ecr.initiate_layer_upload(repositoryName=repo)
    ecr.upload_layer_part(repositoryName=repo, uploadId=up["uploadId"], partFirstByte=0,
                          partLastByte=len(blob) - 1, layerPartBlob=blob)
    ecr.complete_layer_upload(repositoryName=repo, uploadId=up["uploadId"], layerDigests=[digest])
    return digest


cd, ld = upload(config), upload(layer)
manifest = {"schemaVersion": 2, "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
            "config": {"mediaType": "application/vnd.docker.container.image.v1+json", "size": len(config), "digest": cd},
            "layers": [{"mediaType": "application/vnd.docker.image.rootfs.diff.tar.gzip", "size": len(layer), "digest": ld}]}
r = ecr.put_image(repositoryName=repo, imageManifest=json.dumps(manifest), imageTag="latest")
print("pushed", r["image"]["imageId"])
