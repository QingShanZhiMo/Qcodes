"""
The storage-facing module that handles serializations and deserializations
into different versions of the top-level object, the RunDescriber.

Serialization is implemented in two steps: converting RunDescriber objects to
plain python dicts first, and then converting them to plain formats such as
json or yaml.

Moreover this module introduces the following terms for the versions of
RunDescriber object:

- native version: the actual version of a given RunDescriber object or the
actual version encoded in its json (or other) representation
- current version: the version of RunDescriber object that is used within
QCoDeS
- storage version: the version of RunDescriber object that is used by the
data storage infrastructure of QCoDeS

The names of the functions in this module follow the "to_*"/"from_*"
convention where "*" stands for the storage format. Also note the
"as_version", "for_storage", "to_current", "to_native" suffixes.
"""
import io
import json
from typing import Type, Union, cast

from qcodes.utils.helpers import YAML

from .. import rundescriber as current
from . import v0
from .converters import v0_to_v1, v1_to_v0
from .rundescribertypes import RunDescriberV1Dict, RunDescriberV0Dict, RunDescriberDicts

CURRENT_VERSION = 1
# the version of :class:`RunDescriber` object that is used within :mod:`qcodes`
STORAGE_VERSION = 0
# the version of :class:`RunDescriber` object that is used by the data storage
# infrastructure of :mod:`qcodes`


SomeRunDescriber = Union[current.RunDescriber, v0.RunDescriber]
SomeRunDescriberType = Union[Type[v0.RunDescriber],
                             Type[current.RunDescriber]]

# keys: (from_version, to_version)
_converters = {(0, 0): lambda x: x,
               (0, 1): v0_to_v1,
               (1, 0): v1_to_v0,
               (1, 1): lambda x: x}


# python dict


def from_dict_to_native(dct: RunDescriberDicts) -> SomeRunDescriber:
    """
    Convert a dict (usually coming from json.loads) into a RunDescriber
    object according to the version specified in the dict
    """
    dct_version = dct['version']
    if dct_version == 0:
        return v0.RunDescriber._from_dict(cast(RunDescriberV0Dict, dct))
    elif dct_version == 1:
        return current.RunDescriber._from_dict(cast(RunDescriberV1Dict, dct))
    else:
        raise RuntimeError(f"Unknown version of run describer dictionary, can't deserialize. The dictionary is {dct!r}")


def from_dict_to_current(dct: RunDescriberDicts) -> current.RunDescriber:
    """
    Convert a dict into a RunDescriber of the current version
    """
    desc = from_dict_to_native(dct)

    return _converters[(desc.version, CURRENT_VERSION)](desc)


def to_dict_as_version(desc: SomeRunDescriber,
                       version: int) -> RunDescriberDicts:
    """
    Convert the given RunDescriber into a dictionary that represents a
    RunDescriber of the given version
    """
    return _converters[(desc.version, version)](desc)._to_dict()


def to_dict_for_storage(desc: SomeRunDescriber) -> RunDescriberDicts:
    """
    Convert a RunDescriber into a dictionary that represents the
    RunDescriber of the storage version
    """
    return to_dict_as_version(desc, STORAGE_VERSION)


# JSON


def to_json_for_storage(desc: SomeRunDescriber) -> str:
    """
    Serialize the given RunDescriber to JSON as a RunDescriber of the
    version for storage
    """
    return json.dumps(to_dict_for_storage(desc))


def to_json_as_version(desc: SomeRunDescriber, version: int) -> str:
    """
    Serialize the given RunDescriber to JSON as a RunDescriber of the
    given version. Only to be used in tests and upgraders
    """
    return json.dumps(to_dict_as_version(desc, version))


def from_json_to_current(json_str: str) -> current.RunDescriber:
    """
    Deserialize a JSON string into a RunDescriber of the current version
    """
    return from_dict_to_current(json.loads(json_str))


def from_json_to_native(json_str: str) -> SomeRunDescriber:
    """
    Deserialize a JSON string into a RunDescriber of the version given in
    the JSON (native version)
    """
    return from_dict_to_native(json.loads(json_str))


# YAML


def to_yaml_for_storage(desc: SomeRunDescriber) -> str:
    """
    Serialize the given RunDescriber to YAML as a RunDescriber of the
    version for storage
    """
    yaml = YAML()
    with io.StringIO() as stream:
        yaml.dump(to_dict_for_storage(desc), stream=stream)
        output = stream.getvalue()

    return output


def from_yaml_to_current(yaml_str: str) -> current.RunDescriber:
    """
    Deserialize a YAML string into a RunDescriber of the current version
    """
    yaml = YAML()
    # yaml.load returns an OrderedDict, but we need a dict
    ser = cast(RunDescriberDicts, dict(yaml.load(yaml_str)))
    return from_dict_to_current(ser)
