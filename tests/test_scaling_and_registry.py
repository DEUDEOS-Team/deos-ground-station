"""Unit tests for scaling conversions and registry lookups."""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../shared")))

from deos_core import (
    to_physical,
    to_raw,
    get_fault_info,
    get_parameter_info,
    list_parameters,
    NodeId,
    ServiceId,
    FaultSeverity,
    END_OF_FAULT_LIST,
)


class TestScalingAndRegistry(unittest.TestCase):
    def test_traction_scaling(self):
        # Speed: scale 0.01 m/s. 725 raw -> 7.25 m/s
        self.assertEqual(to_physical(725, 0.01), 7.25)
        self.assertEqual(to_raw(7.25, 0.01), 725)

        # Current: scale 0.1 A. 154 raw -> 15.4 A
        self.assertEqual(to_physical(154, 0.1), 15.4)
        self.assertEqual(to_raw(15.4, 0.1), 154)

    def test_steering_scaling(self):
        # Angle: scale 0.01 deg. -1250 raw -> -12.50 deg
        self.assertEqual(to_physical(-1250, 0.01), -12.5)
        self.assertEqual(to_raw(-12.5, 0.01), -1250)

    def test_bms_cell_voltage_scaling(self):
        # Cell voltage: scale 0.001 V. 3652 raw -> 3.652 V
        self.assertEqual(to_physical(3652, 0.001, decimals=3), 3.652)
        self.assertEqual(to_raw(3.652, 0.001), 3652)

    def test_fault_registry_common_and_nodes(self):
        # 0x0000 is END_OF_FAULT_LIST
        f0 = get_fault_info(NodeId.TRACTION, END_OF_FAULT_LIST)
        self.assertEqual(f0.code, 0x0000)
        self.assertEqual(f0.name, "END_OF_FAULT_LIST")

        # 0x0010 is Subscription Table Full (DEOS_FAULT_SUB_TABLE_FULL)
        f_sub = get_fault_info(NodeId.MAIN_STM32, 0x0010)
        self.assertIn(f_sub.name, ("SUB_TABLE_FULL", "SUBSCRIPTION_TABLE_FULL"))

        # 0x0100 on Traction: Motor Comm Lost
        f_trac = get_fault_info(NodeId.TRACTION, 0x0100)
        self.assertEqual(f_trac.name, "MOTOR_COMM_LOST")
        self.assertEqual(f_trac.default_severity, FaultSeverity.CRITICAL)

        # 0x0100 on Steering: Steering Encoder Comm Lost
        f_str = get_fault_info(NodeId.STEERING, 0x0100)
        self.assertEqual(f_str.name, "STEER_ENCODER_COMM_LOST")

        # 0x0100 on BMS Main: Pack Overvoltage
        f_bms = get_fault_info(NodeId.BMS_MAIN, 0x0100)
        self.assertEqual(f_bms.name, "PACK_OVERVOLTAGE")

    def test_parameter_registry(self):
        p_kp = get_parameter_info(ServiceId.TRACTION, 0x0001)
        self.assertIsNotNone(p_kp)
        self.assertEqual(p_kp.name, "PID_KP")
        self.assertEqual(p_kp.scale, 0.01)

        p_angle = get_parameter_info(ServiceId.STEERING, 0x0010)
        self.assertIsNotNone(p_angle)
        self.assertEqual(p_angle.name, "ZERO_OFFSET")
        self.assertEqual(p_angle.unit, "deg")

        trac_params = list_parameters(ServiceId.TRACTION)
        self.assertTrue(len(trac_params) >= 10)


if __name__ == "__main__":
    unittest.main()

