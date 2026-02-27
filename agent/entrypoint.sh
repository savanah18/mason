#!/bin/bash
OCI_REGISTRY_SECRET="/run/secrets/oci-registry"
if [ -f "$OCI_REGISTRY_SECRET" ]; then
  source "$OCI_REGISTRY_SECRET"
  echo "Loaded OCI registry credentials from $OCI_REGISTRY_SECRET"
  
  # Export variables to make them available to child processes
  export REGISTRY_USERNAME
  export REGISTRY_PASSWORD
  
  if [ -z "$REGISTRY_USERNAME" ]; then
    echo "Warning: REGISTRY_USERNAME is not set in $OCI_REGISTRY_SECRET"
  fi
else
  echo "Warning: OCI registry secret file not found at $OCI_REGISTRY_SECRET"
fi

# Run the container's main command
exec "$@"