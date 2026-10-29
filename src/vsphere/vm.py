"""Create the requested VM on vcsim through pyVmomi, the vSphere API client.

vcsim (govmomi) answers the real vSphere API but runs nothing: the VM exists in the inventory,
with its folder, size and network, and nothing more. Sizes, folder and names come from
referentiel/netco.yaml (VM-01).
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlsplit

from pyVim.connect import Disconnect, SmartConnect
from pyVim.task import WaitForTask
from pyVmomi import vim, vmodl

from netco.rules import load_rules

DATACENTER, CLUSTER, DATASTORE = "DC0", "DC0_C0", "LocalDS_0"  # vcsim default inventory
PLATFORM = "vcsim (simulateur de l'API vSphere)"
PROPERTIES = [
    "runtime.powerState",
    "config.hardware.numCPU",
    "config.hardware.memoryMB",
    "config.instanceUuid",
]


@contextmanager
def connect() -> Iterator[Any]:
    url = urlsplit(os.environ.get("VCSIM_URL", "https://localhost:8989/sdk"))
    # The simulator serves a self-signed certificate; it accepts any user name and password.
    si = SmartConnect(
        host=url.hostname,
        port=url.port or 443,
        user=url.username or "user",
        pwd=url.password or "pass",
        disableSslCertValidation=True,
    )
    try:
        yield si.RetrieveContent()
    finally:
        Disconnect(si)


def _child(folder: Any, name: str, kind: type) -> Any:
    return next((c for c in folder.childEntity if c.name == name and isinstance(c, kind)), None)


def _datacenter(content: Any) -> Any:
    return next(dc for dc in content.rootFolder.childEntity if dc.name == DATACENTER)


def _folder(datacenter: Any, path: str, create: bool) -> Any:
    folder = datacenter.vmFolder
    for part in path.split("/"):
        child = _child(folder, part, vim.Folder)
        if child is None:
            if not create:
                return None
            child = folder.CreateFolder(part)
        folder = child
    return folder


def _properties(content: Any, vm: Any) -> dict[str, Any]:
    # Read by path: vcsim returns an empty runtime.faultToleranceState that pyVmomi cannot parse,
    # so vm.runtime and vm.summary fail as a whole.
    collector = vmodl.query.PropertyCollector
    spec = collector.FilterSpec(
        objectSet=[collector.ObjectSpec(obj=vm)],
        propSet=[collector.PropertySpec(type=vim.VirtualMachine, pathSet=PROPERTIES)],
    )
    return {p.name: p.val for p in content.propertyCollector.RetrieveContents([spec])[0].propSet}


def _describe(content: Any, vm: Any, folder: str) -> dict[str, Any]:
    props = _properties(content, vm)
    return {
        "name": vm.name,
        "folder": folder,
        "cpu": props["config.hardware.numCPU"],
        "memoryMb": props["config.hardware.memoryMB"],
        "network": ", ".join(sorted(n.name for n in vm.network)),
        "powerState": str(props["runtime.powerState"]),
        "uuid": props["config.instanceUuid"],
        "platform": PLATFORM,
    }


def _names(service: str, environment: str) -> tuple[str, str]:
    rules = load_rules()["vm"]
    return (
        rules["folder_template"].format(environment=environment),
        rules["name_template"].format(service=service, environment=environment),
    )


def ensure_vm(service: str, environment: str, size: str) -> dict[str, Any]:
    """Create (or find) the VM of an exposure and power it on; idempotent."""
    rules = load_rules()["vm"]
    spec = rules["sizes"][size]
    folder_path, name = _names(service, environment)
    with connect() as content:
        datacenter = _datacenter(content)
        folder = _folder(datacenter, folder_path, create=True)
        vm = _child(folder, name, vim.VirtualMachine)
        if vm is None:
            network = next(n for n in datacenter.network if n.name == rules["network"])
            nic = vim.vm.device.VirtualDeviceSpec(
                operation=vim.vm.device.VirtualDeviceSpec.Operation.add,
                device=vim.vm.device.VirtualVmxnet3(
                    backing=vim.vm.device.VirtualEthernetCard.NetworkBackingInfo(
                        deviceName=rules["network"], network=network
                    )
                ),
            )
            config = vim.vm.ConfigSpec(
                name=name,
                numCPUs=spec["cpu"],
                memoryMB=spec["memory_mb"],
                guestId="otherLinux64Guest",
                files=vim.vm.FileInfo(vmPathName=f"[{DATASTORE}]"),
                deviceChange=[nic],
                annotation=f"NetCo (entreprise fictive) : VM de {service} en {environment}",
            )
            cluster = _child(datacenter.hostFolder, CLUSTER, vim.ClusterComputeResource)
            WaitForTask(folder.CreateVM_Task(config=config, pool=cluster.resourcePool))
            vm = _child(folder, name, vim.VirtualMachine)
        if _properties(content, vm)["runtime.powerState"] != "poweredOn":
            WaitForTask(vm.PowerOnVM_Task())
        return _describe(content, vm, folder_path)


def find_vm(service: str, environment: str) -> dict[str, Any] | None:
    """Read-only lookup, used by the e2e checks."""
    folder_path, name = _names(service, environment)
    with connect() as content:
        folder = _folder(_datacenter(content), folder_path, create=False)
        vm = _child(folder, name, vim.VirtualMachine) if folder is not None else None
        return _describe(content, vm, folder_path) if vm is not None else None
