#!/usr/bin/env bash
# Undoes setup.sh on an edge PC so it can be run again (for example after it
# failed halfway): stops and removes the Greengrass service, /greengrass and
# ggc_user, and the OpenLUTRA containers. Run as root: cleanup.sh [--images] [--data]
#
#   --images  also remove the OpenLUTRA images pulled by Greengrass
#   --data    also remove the recordings (/var/lib/open-lutra)
#
# Docker, Java and the other packages setup.sh installed are kept. The device's
# Thing and certificate in AWS are not touched; set it up again with the same bundle.
set -euo pipefail

remove_images=false
remove_data=false
for arg in "$@"; do
  case "$arg" in
    --images) remove_images=true ;;
    --data) remove_data=true ;;
    *) echo "usage: cleanup.sh [--images] [--data]" >&2; exit 1 ;;
  esac
done

if [ "$(id -u)" -ne 0 ]; then
  echo "run as root" >&2
  exit 1
fi

if systemctl cat greengrass.service >/dev/null 2>&1; then
  systemctl disable --now greengrass.service || true
  rm -f /etc/systemd/system/greengrass.service
  systemctl daemon-reload
  echo "removed the greengrass service"
fi

if command -v docker >/dev/null; then
  docker compose -p open-lutra down --remove-orphans || true
  if $remove_images; then
    images=$(docker images --format '{{.Repository}}:{{.Tag}}' | grep -E '/open-lutra-(backend|frontend):' || true)
    # shellcheck disable=SC2086 # one argument per image
    [ -z "$images" ] || docker rmi $images
  fi
fi

rm -rf /greengrass
echo "removed /greengrass"

id ggc_user >/dev/null 2>&1 && userdel -r ggc_user 2>/dev/null || true
getent group ggc_group >/dev/null && groupdel ggc_group || true

if $remove_data; then
  rm -rf /var/lib/open-lutra
  echo "removed /var/lib/open-lutra"
else
  [ -d /var/lib/open-lutra ] && echo "kept the recordings in /var/lib/open-lutra (remove them with --data)"
fi

echo "cleanup done; run setup.sh again to set this device up"
