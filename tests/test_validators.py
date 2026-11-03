from app import validators as v


def test_pan_valid_format_passes_without_warnings():
    check = v.validate_pan("abpce1234f")  # 4th letter C = company holder type
    assert check.valid and check.value == "ABPCE1234F" and check.warnings == []


def test_pan_wrong_shape_is_an_error():
    check = v.validate_pan("ABCDE12345")
    assert not check.valid and "PAN must be" in check.errors[0]


def test_pan_unusual_holder_code_is_a_warning_not_a_rejection():
    check = v.validate_pan("ABCDE1234F")  # 4th letter D is not a standard holder code
    assert check.valid and check.warnings


def test_aadhaar_generated_checksum_verifies_cleanly():
    base = "23456789012"
    full = base + v.verhoeff_check_digit(base)
    check = v.validate_aadhaar(full)
    assert check.valid and check.warnings == []


def test_aadhaar_sample_number_is_flagged_not_silently_accepted():
    check = v.validate_aadhaar("1234 5678 9012")
    assert check.valid and len(check.warnings) == 2


def test_aadhaar_wrong_length_is_rejected():
    assert not v.validate_aadhaar("1234 5678 901").valid


def test_gstin_known_good_value_passes():
    check = v.validate_gstin("27AAPFU0939F1ZV")
    assert check.valid and check.warnings == []
    assert v.embedded_pan_from_gstin(check.value) == "AAPFU0939F"


def test_gstin_wrong_check_character_is_a_warning():
    check = v.validate_gstin("27AAPFU0939F1Z9")
    assert check.valid and check.warnings


def test_gstin_bad_state_code_is_rejected():
    assert not v.validate_gstin("99AAPFU0939F1ZV").valid


def test_name_similarity_ignores_case_and_spacing():
    assert v.name_similarity("ROHAN  MEHTA", "rohan mehta") == 1.0
    assert v.name_similarity("SUNITA TRADERS", "ROHAN MEHTA") < 0.5


def test_mask_keeps_only_last_four_digits():
    assert v.mask_aadhaar("123456789012") == "XXXX XXXX 9012"
