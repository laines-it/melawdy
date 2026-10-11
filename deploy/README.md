# Deployment notes

The VPS deployment for `lawmposer.ru` uses the existing k3s cluster in an isolated `melawdy` namespace, as explicitly authorized for publication. See [k3s deployment and operations](k3s/README.md). Local development continues to use Docker Compose.

The root `docker-compose.yml` is a single-host development stack. For a deployment, publish versioned images for `web` and `api`, set unique secrets through the target platform, and expose only the web entrypoint through the platform's existing ingress or reverse proxy. PostgreSQL and MinIO should remain private to the application network.

The MinIO Dockerfile uses the community-maintained `ghcr.io/coollabsio/minio` image built from versioned MinIO releases because upstream no longer publishes the image under its former Docker Hub repository. Keep the release tag pinned and review its source before production use.

Before production use, define backup/restore procedures for PostgreSQL and MinIO, configure TLS and domain routing, review resource limits, and replace the ML placeholder with the intended model/runtime. Keep deployment-specific secrets out of this repository.
