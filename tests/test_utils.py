""" Tests for the contents of utils.py. """


import unittest, utils


""" Tests to make sure phone number validation works properly. """
class TestPhoneNumbers(unittest.TestCase):
  """ Tests that standard phone numbers work and that bad ones don't work. """
  def test_phone(self):
    self.assertFalse(utils.is_phone_valid('898-7925'))
    self.assertFalse(utils.is_phone_valid('898-7925 x1234'))
    self.assertFalse(utils.is_phone_valid('8985-7925'))
    self.assertFalse(utils.is_phone_valid('8987925'))
    self.assertTrue(utils.is_phone_valid('(650) 898-7925'))
    self.assertTrue(utils.is_phone_valid('(650) 898-7925 x1234'))
    self.assertTrue(utils.is_phone_valid('6508987925'))
    self.assertFalse(utils.is_phone_valid('65089879251234'))
    self.assertFalse(utils.is_phone_valid('89879251234'))
    self.assertTrue(utils.is_phone_valid('6508987925x1234'))
    self.assertFalse(utils.is_phone_valid('89879251234'))
    self.assertFalse(utils.is_phone_valid('foo bar'))
