import textwrap
from typing import Optional, Dict, Any, Union, TYPE_CHECKING
import numpy as np
import qcodes.utils.validators as vals
from qcodes.utils.validators import Arrays

from .KeysightB1500_sampling_measurement import SamplingMeasurement
from .KeysightB1500_module import B1500Module, parse_spot_measurement_response
from .message_builder import MessageBuilder
from . import constants
from .constants import ModuleKind, ChNr, AAD, MM
if TYPE_CHECKING:
    from .KeysightB1500 import KeysightB1500


class B1517A(B1500Module):
    """
    Driver for Keysight B1517A Source/Monitor Unit module for B1500
    Semiconductor Parameter Analyzer.

    Args:
        parent: mainframe B1500 instance that this module belongs to
        name: Name of the instrument instance to create. If `None`
            (Default), then the name is autogenerated from the instrument
            class.
        slot_nr: Slot number of this module (not channel number)
    """
    MODULE_KIND = ModuleKind.SMU
    _interval_validator = vals.Numbers(0.0001, 65.535)

    def __init__(self, parent: 'KeysightB1500', name: Optional[str], slot_nr,
                 **kwargs):
        super().__init__(parent, name, slot_nr, **kwargs)
        self.channels = (ChNr(slot_nr),)
        self._measure_config: Dict[str, Optional[Any]] = {
            k: None for k in ("measure_range",)}
        self._source_config: Dict[str, Optional[Any]] = {
            k: None for k in ("output_range", "compliance",
                              "compl_polarity", "min_compliance_range")}
        self._timing_parameters: Dict[str, Optional[Any]] = {
            k: None for k in ("h_bias", "interval", "number", "h_base")}

        # We want to snapshot these configuration dictionaries
        self._meta_attrs += ['_measure_config', '_source_config',
                             '_timing_parameters']

        self.add_parameter(
            name="measurement_mode",
            get_cmd=None,
            set_cmd=self._set_measurement_mode,
            set_parser=MM.Mode,
            vals=vals.Enum(*list(MM.Mode)),
            docstring=textwrap.dedent("""
                Set measurement mode for this module.
                
                It is recommended for this parameter to use values from 
                :class:`.constants.MM.Mode` enumeration.
                
                Refer to the documentation of ``MM`` command in the 
                programming guide for more information.""")
        )
        # Instrument is initialized with this setting having value of
        # `1`, spot measurement mode, hence let's set the parameter to this
        # value since it is not possible to request this value from the
        # instrument.
        self.measurement_mode.cache.set(MM.Mode.SPOT)

        self.add_parameter(
            name="voltage",
            set_cmd=self._set_voltage,
            get_cmd=self._get_voltage,
            snapshot_get=False
        )

        self.add_parameter(
            name="current",
            set_cmd=self._set_current,
            get_cmd=self._get_current,
            snapshot_get=False
        )

        self.add_parameter(
            name="time_axis",
            get_cmd=self._get_time_axis,
            vals=Arrays(shape=(self._get_number_of_samples,)),
            snapshot_value=False,
            label='Time',
            unit='s'
        )

        self.add_parameter(
            name="sampling_measurement_trace",
            parameter_class=SamplingMeasurement,
            vals=Arrays(shape=(self._get_number_of_samples,)),
            setpoints=(self.time_axis,)
        )

    def _get_number_of_samples(self) -> int:
        if self._timing_parameters['number'] is not None:
            sample_number = self._timing_parameters['number']
            return sample_number
        else:
            raise Exception('set timing parameters first')

    def _get_time_axis(self) -> np.ndarray:
        sample_rate = self._timing_parameters['interval']
        total_time = self._total_measurement_time()
        time_xaxis = np.arange(0, total_time, sample_rate)
        return time_xaxis

    def _total_measurement_time(self) -> float:
        if self._timing_parameters['interval'] is None or \
                self._timing_parameters['number'] is None:
            raise Exception('set timing parameters first')

        sample_number = self._timing_parameters['number']
        sample_rate = self._timing_parameters['interval']
        total_time = float(sample_rate * sample_number)
        return total_time

    def _set_voltage(self, value: float) -> None:
        if self._source_config["output_range"] is None:
            self._source_config["output_range"] = constants.VOutputRange.AUTO
        if not isinstance(self._source_config["output_range"],
                          constants.VOutputRange):
            raise TypeError(
                "Asking to force voltage, but source_config contains a "
                "current output range"
            )
        msg = MessageBuilder().dv(
            chnum=self.channels[0],
            v_range=self._source_config["output_range"],
            voltage=value,
            i_comp=self._source_config["compliance"],
            comp_polarity=self._source_config["compl_polarity"],
            i_range=self._source_config["min_compliance_range"],
        )
        self.write(msg.message)

    def _set_current(self, value: float) -> None:
        if self._source_config["output_range"] is None:
            self._source_config["output_range"] = constants.IOutputRange.AUTO
        if not isinstance(self._source_config["output_range"],
                          constants.IOutputRange):
            raise TypeError(
                "Asking to force current, but source_config contains a "
                "voltage output range"
            )
        msg = MessageBuilder().di(
            chnum=self.channels[0],
            i_range=self._source_config["output_range"],
            current=value,
            v_comp=self._source_config["compliance"],
            comp_polarity=self._source_config["compl_polarity"],
            v_range=self._source_config["min_compliance_range"],
        )
        self.write(msg.message)

    def _get_current(self) -> float:
        msg = MessageBuilder().ti(
            chnum=self.channels[0],
            i_range=self._measure_config["measure_range"],
        )
        response = self.ask(msg.message)

        parsed = parse_spot_measurement_response(response)
        return parsed["value"]

    def _get_voltage(self) -> float:
        msg = MessageBuilder().tv(
            chnum=self.channels[0],
            v_range=self._measure_config["measure_range"],
        )
        response = self.ask(msg.message)

        parsed = parse_spot_measurement_response(response)
        return parsed["value"]

    def _set_measurement_mode(self, mode: Union[MM.Mode, int]) -> None:
        self.write(MessageBuilder()
                   .mm(mode=mode,
                       channels=[self.channels[0]])
                   .message)

    def source_config(
            self,
            output_range: constants.OutputRange,
            compliance: Optional[Union[float, int]] = None,
            compl_polarity: Optional[constants.CompliancePolarityMode] = None,
            min_compliance_range: Optional[constants.OutputRange] = None,
    ) -> None:
        """Configure sourcing voltage/current

        Args:
            output_range: voltage/current output range
            compliance: voltage/current compliance value
            compl_polarity: compliance polarity mode
            min_compliance_range: minimum voltage/current compliance output
                range
        """
        if min_compliance_range is not None:
            if isinstance(min_compliance_range, type(output_range)):
                raise TypeError(
                    "When forcing voltage, min_compliance_range must be an "
                    "current output range (and vice versa)."
                )

        self._source_config = {
            "output_range": output_range,
            "compliance": compliance,
            "compl_polarity": compl_polarity,
            "min_compliance_range": min_compliance_range,
        }

    def measure_config(self, measure_range: constants.MeasureRange) -> None:
        """Configure measuring voltage/current

        Args:
            measure_range: voltage/current measurement range
        """
        self._measure_config = {"measure_range": measure_range}

    def timing_parameters(self,
                          h_bias: float,
                          interval: float,
                          number: int,
                          h_base: Optional[float] = None
                          ) -> None:
        """
        This command sets the timing parameters of the sampling measurement
        mode (:attr:`.MM.Mode.SAMPLING`, ``10``).

        Refer to the programming guide for more information about the ``MT``
        command, especially for notes on sampling operation and about setting
        interval < 0.002 s.

        Args:
            h_bias: Time since the bias value output until the first
                sampling point. Numeric expression. in seconds.
                0 (initial setting) to 655.35 s, resolution 0.01 s.
                The following values are also available for interval < 0.002 s.
                ``|h_bias|`` will be the time since the sampling start until
                the bias value output. -0.09 to -0.0001 s, resolution 0.0001 s.
            interval: Interval of the sampling. Numeric expression,
                0.0001 to 65.535, in seconds. Initial value is 0.002.
                Resolution is 0.001 at interval < 0.002. Linear sampling of
                interval < 0.002 in 0.00001 resolution is available
                only when the following formula is satisfied.
                ``interval >= 0.0001 + 0.00002 * (number of measurement
                channels-1)``
            number: Number of samples. Integer expression. 1 to the
                following value. Initial value is 1000. For the linear
                sampling: ``100001 / (number of measurement channels)``.
                For the log sampling: ``1 + (number of data for 11 decades)``
            h_base: Hold time of the base value output until the bias value
                output. Numeric expression. in seconds. 0 (initial setting)
                to 655.35 s, resolution 0.01 s.
        """
        # The duplication of kwargs in the calls below is due to the
        # difference in type annotations between ``MessageBuilder.mt()``
        # method and ``_timing_parameters`` attribute.

        self._interval_validator.validate(interval)
        self._timing_parameters.update(h_bias=h_bias,
                                       interval=interval,
                                       number=number,
                                       h_base=h_base)
        self.write(MessageBuilder()
                   .mt(h_bias=h_bias,
                       interval=interval,
                       number=number,
                       h_base=h_base)
                   .message)

    def use_high_speed_adc(self) -> None:
        """Use high-speed ADC type for this module/channel"""
        self.write(MessageBuilder()
                   .aad(chnum=self.channels[0],
                        adc_type=AAD.Type.HIGH_SPEED)
                   .message)

    def use_high_resolution_adc(self) -> None:
        """Use high-resolution ADC type for this module/channel"""
        self.write(MessageBuilder()
                   .aad(chnum=self.channels[0],
                        adc_type=AAD.Type.HIGH_RESOLUTION)
                   .message)