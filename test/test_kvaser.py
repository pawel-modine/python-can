#!/usr/bin/env python
# coding: utf-8

"""
"""

import time
import unittest
from unittest.mock import Mock

import pytest

import can
from can.interfaces.kvaser import canlib
from can.interfaces.kvaser import constants


class KvaserTest(unittest.TestCase):
    def setUp(self):
        canlib.canGetNumberOfChannels = KvaserTest.canGetNumberOfChannels
        canlib.canOpenChannel = Mock(return_value=0)
        canlib.canIoCtl = Mock(return_value=0)
        canlib.kvReadTimer = Mock()
        canlib.canSetBusParams = Mock()
        canlib.canSetBusParamsFd = Mock()
        canlib.canBusOn = Mock()
        canlib.canBusOff = Mock()
        canlib.canClose = Mock()
        canlib.canSetBusOutputControl = Mock()
        canlib.canGetChannelData = Mock()
        canlib.canSetAcceptanceFilter = Mock()
        canlib.canWriteSync = Mock()
        canlib.canWrite = self.canWrite
        canlib.canReadWait = self.canReadWait
        canlib.canGetBusStatistics = Mock()
        canlib.canRequestBusStatistics = Mock()

        self.msg = {}
        self.msg_in_cue = None
        self.bus = can.Bus(channel=0, bustype="kvaser")

    def tearDown(self):
        if self.bus:
            self.bus.shutdown()
            self.bus = None

    def test_bus_creation(self):
        self.assertIsInstance(self.bus, canlib.KvaserBus)
        self.assertTrue(canlib.canOpenChannel.called)
        self.assertTrue(canlib.canBusOn.called)

    def test_bus_shutdown(self):
        self.bus.shutdown()
        self.assertTrue(canlib.canBusOff.called)
        self.assertTrue(canlib.canClose.called)

    def test_filter_setup(self):
        # No filter in constructor
        expected_args = [
            ((0, 0, 0, 0),),  # Disable filtering STD on read handle
            ((0, 0, 0, 1),),  # Disable filtering EXT on read handle
            ((0, 0, 0, 0),),  # Disable filtering STD on write handle
            ((0, 0, 0, 1),),  # Disable filtering EXT on write handle
        ]
        self.assertEqual(canlib.canSetAcceptanceFilter.call_args_list, expected_args)

        # One filter, will be handled by canlib
        canlib.canSetAcceptanceFilter.reset_mock()
        self.bus.set_filters([{"can_id": 0x8, "can_mask": 0xFF, "extended": True}])
        expected_args = [
            ((0, 0x8, 0xFF, 1),),  # Enable filtering EXT on read handle
            ((0, 0x8, 0xFF, 1),),  # Enable filtering EXT on write handle
        ]
        self.assertEqual(canlib.canSetAcceptanceFilter.call_args_list, expected_args)

        # Multiple filters, will be handled in Python
        canlib.canSetAcceptanceFilter.reset_mock()
        multiple_filters = [
            {"can_id": 0x8, "can_mask": 0xFF},
            {"can_id": 0x9, "can_mask": 0xFF},
        ]
        self.bus.set_filters(multiple_filters)
        expected_args = [
            ((0, 0, 0, 0),),  # Disable filtering STD on read handle
            ((0, 0, 0, 1),),  # Disable filtering EXT on read handle
            ((0, 0, 0, 0),),  # Disable filtering STD on write handle
            ((0, 0, 0, 1),),  # Disable filtering EXT on write handle
        ]
        self.assertEqual(canlib.canSetAcceptanceFilter.call_args_list, expected_args)

    def test_send_extended(self):
        msg = can.Message(
            arbitration_id=0xC0FFEE, data=[0, 25, 0, 1, 3, 1, 4], is_extended_id=True
        )

        self.bus.send(msg)

        self.assertEqual(self.msg["arb_id"], 0xC0FFEE)
        self.assertEqual(self.msg["dlc"], 7)
        self.assertEqual(self.msg["flags"], constants.canMSG_EXT)
        self.assertSequenceEqual(self.msg["data"], [0, 25, 0, 1, 3, 1, 4])

    def test_send_standard(self):
        msg = can.Message(arbitration_id=0x321, data=[50, 51], is_extended_id=False)

        self.bus.send(msg)

        self.assertEqual(self.msg["arb_id"], 0x321)
        self.assertEqual(self.msg["dlc"], 2)
        self.assertEqual(self.msg["flags"], constants.canMSG_STD)
        self.assertSequenceEqual(self.msg["data"], [50, 51])

    @pytest.mark.timeout(3.0)
    def test_recv_no_message(self):
        self.assertEqual(self.bus.recv(timeout=0.5), None)

    def test_recv_extended(self):
        self.msg_in_cue = can.Message(
            arbitration_id=0xC0FFEF, data=[1, 2, 3, 4, 5, 6, 7, 8], is_extended_id=True
        )

        now = time.time()
        msg = self.bus.recv()
        self.assertEqual(msg.arbitration_id, 0xC0FFEF)
        self.assertEqual(msg.dlc, 8)
        self.assertEqual(msg.is_extended_id, True)
        self.assertSequenceEqual(msg.data, self.msg_in_cue.data)
        self.assertTrue(now - 1 < msg.timestamp < now + 1)

    def test_recv_standard(self):
        self.msg_in_cue = can.Message(
            arbitration_id=0x123, data=[100, 101], is_extended_id=False
        )

        msg = self.bus.recv()
        self.assertEqual(msg.arbitration_id, 0x123)
        self.assertEqual(msg.dlc, 2)
        self.assertEqual(msg.is_extended_id, False)
        self.assertSequenceEqual(msg.data, [100, 101])

    def test_available_configs(self):
        configs = canlib.KvaserBus._detect_available_configs()
        expected = [
            {"interface": "kvaser", "channel": 0},
            {"interface": "kvaser", "channel": 1},
        ]
        self.assertListEqual(configs, expected)

    def test_canfd_default_data_bitrate(self):
        canlib.canSetBusParams.reset_mock()
        canlib.canSetBusParamsFd.reset_mock()
        can.Bus(channel=0, bustype="kvaser", fd=True)
        canlib.canSetBusParams.assert_called_once_with(
            0, constants.canFD_BITRATE_500K_80P, 0, 0, 0, 0, 0
        )
        canlib.canSetBusParamsFd.assert_called_once_with(
            0, constants.canFD_BITRATE_500K_80P, 0, 0, 0
        )

    def test_canfd_nondefault_data_bitrate(self):
        canlib.canSetBusParams.reset_mock()
        canlib.canSetBusParamsFd.reset_mock()
        data_bitrate = 2000000
        can.Bus(channel=0, bustype="kvaser", fd=True, data_bitrate=data_bitrate)
        bitrate_constant = canlib.BITRATE_FD[data_bitrate]
        canlib.canSetBusParams.assert_called_once_with(
            0, constants.canFD_BITRATE_500K_80P, 0, 0, 0, 0, 0
        )
        canlib.canSetBusParamsFd.assert_called_once_with(0, bitrate_constant, 0, 0, 0)

    def test_canfd_custom_data_bitrate(self):
        canlib.canSetBusParams.reset_mock()
        canlib.canSetBusParamsFd.reset_mock()
        data_bitrate = 123456
        can.Bus(channel=0, bustype="kvaser", fd=True, data_bitrate=data_bitrate)
        canlib.canSetBusParams.assert_called_once_with(
            0, constants.canFD_BITRATE_500K_80P, 0, 0, 0, 0, 0
        )
        canlib.canSetBusParamsFd.assert_called_once_with(0, data_bitrate, 0, 0, 0)

    def test_bus_get_stats(self):
        stats = self.bus.get_stats()
        self.assertTrue(canlib.canRequestBusStatistics.called)
        self.assertTrue(canlib.canGetBusStatistics.called)
        self.assertIsInstance(stats, canlib.structures.BusStatistics)

    @staticmethod
    def canGetNumberOfChannels(count):
        count._obj.value = 2

    def canWrite(self, handle, arb_id, buf, dlc, flags):
        self.msg["arb_id"] = arb_id
        self.msg["dlc"] = dlc
        self.msg["flags"] = flags
        self.msg["data"] = bytearray(buf._obj)

    def canReadWait(self, handle, arb_id, data, dlc, flags, timestamp, timeout):
        if not self.msg_in_cue:
            return constants.canERR_NOMSG

        arb_id._obj.value = self.msg_in_cue.arbitration_id
        dlc._obj.value = self.msg_in_cue.dlc
        data._obj.raw = self.msg_in_cue.data
        flags_temp = 0
        if self.msg_in_cue.is_extended_id:
            flags_temp |= constants.canMSG_EXT
        else:
            flags_temp |= constants.canMSG_STD
        if self.msg_in_cue.is_remote_frame:
            flags_temp |= constants.canMSG_RTR
        if self.msg_in_cue.is_error_frame:
            flags_temp |= constants.canMSG_ERROR_FRAME
        flags._obj.value = flags_temp
        timestamp._obj.value = 0

        return constants.canOK


if __name__ == "__main__":
    unittest.main()
