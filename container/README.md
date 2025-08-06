# Apptainer Container

## Installation

Apptainer can be installed on Ubuntu or within Windows Subsystem for Linux (WSL2).

```bash
sudo apt-get update && sudo apt-get install -y apptainer
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
