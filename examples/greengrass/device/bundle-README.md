# Setting up {thing}

This folder contains everything needed to set up an edge PC (Ubuntu) as the AWS IoT Greengrass device `{thing}`.

- Thing Group: `{thing_group}`
- Certificate issued: {created_at}

`{thing}/` contains the private key. Do not hand it to others or put it in a shared folder.

## Contents

| File | Contents |
|---|---|
| `setup.sh` | Script that sets up the device |
| `cleanup.sh` | Script that removes what `setup.sh` installed, when setup fails |
| `{thing}/` | Certificate, private key, and connection settings |

## Set up

The edge PC must be connected to the internet (it downloads Docker, Java, and Greengrass).

```shell
# Run in the extracted folder (takes a few minutes)
sudo bash setup.sh {thing}

# Check that Greengrass is running. "active (running)" means success
sudo systemctl status greengrass
```

After a few minutes, the OpenLUTRA deployed to `{thing_group}` arrives. Open `http://localhost:5173` in a browser to see the OpenLUTRA screen.

## When done

Once it works, delete this folder and the zip. The certificate and private key have been copied to `/greengrass/v2`, so deleting them does not affect operation.

```shell
cd ..
rm -rf <this folder> <downloaded zip>
```

Ask the operator to delete the private key of `{thing}` from "Secrets" in Fleet Console.

## If it fails

Check the log.

```shell
sudo tail -n 100 /greengrass/v2/logs/greengrass.log
```

If `setup.sh` fails partway, or says "already set up" and cannot be rerun, remove it with `cleanup.sh`, then run `setup.sh` again.

```shell
sudo bash cleanup.sh
sudo bash setup.sh {thing}
```

`cleanup.sh` keeps the recording data (`/var/lib/open-lutra`), Docker, and Java. Add `--data` to also remove the recording data, and `--images` to also remove the OpenLUTRA images.

On a PC connected to both the robot's LAN and the internet, the default route must point to the internet side. If the robot's LAN hands out a gateway, traffic to AWS flows to the robot side and cannot connect.
