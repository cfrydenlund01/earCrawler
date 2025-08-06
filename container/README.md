# Apptainer Container

## Installation

Apptainer can be installed on Ubuntu or within Windows Subsystem for Linux (WSL2).
The package is not available in some default repositories. If `apt` cannot
find `apptainer`, install it via Snap:

```bash
sudo snap install apptainer --classic
```

## Build the Container

Use the provided [earcrawler.def](earcrawler.def) to create a writable sandbox image:

```bash
apptainer build --sandbox earcrawler_sandbox container/earcrawler.def
```

## Run the Container

Execute programs inside the container with GPU support:

```bash
apptainer exec --nv earcrawler_sandbox python train.py --config <config_path>
```
