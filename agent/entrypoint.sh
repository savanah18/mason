#!/bin/bash
OCI_REGISTRY_SECRET="/run/secrets/oci-registry"
source $OCI_REGISTRY_SECRET
if [ -z "$REGISTRY_USERNAME" ] || [ -z "$REGISTRY_PASSWORD" ]; then
  echo "OCI registry credentials are not set. Expected mount path at $OCI_REGISTRY_SECRET"
fi

# Run the container's main command
exec "$@"