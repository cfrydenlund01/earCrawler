from dataclasses import dataclass


@dataclass
class QuantConfig:
    """Simple quantization configuration for tests.

    Attributes
    ----------
    bits: int
        Number of quantization bits. Defaults to 4.
    quant_type: str
        Type of quantization algorithm. Defaults to "nf4".
    """

    bits: int
    quant_type: str = "nf4"


def get_quant_config(bits: int = 4, quant_type: str = "nf4") -> QuantConfig:
    """Return a :class:`QuantConfig` instance.

    Parameters
    ----------
    bits: int, optional
        Number of quantization bits. Defaults to ``4``.
    quant_type: str, optional
        Quantization type. Defaults to ``"nf4"``.
    """
    return QuantConfig(bits=bits, quant_type=quant_type)
