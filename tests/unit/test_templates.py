'''
PyLisC: unit tests for frames mode filename template
'''

# Import external libraries
import pytest

# Import internal functions
from pylisc.templates import compile_template, extract_tilt_angle

class TestTemplates:
    def test_extracts_tilt_and_ignores_blank_fields(self):
        pattern = compile_template('{}_{position}_{}_{tilt}_{}_{}_{}_{}_{}.mrc')
        filename = 'Position_012_003_-30.00_20240115_1_Fractions_motion_corrected.mrc'
        assert extract_tilt_angle(filename, pattern) == pytest.approx(-30.00)
        assert pattern.match(filename).group('position') == '012'

    def test_no_match_raises(self):
        pattern = compile_template('{}_{tilt}.mrc')
        with pytest.raises(ValueError):
            extract_tilt_angle('completely_different_name.mrc', pattern)

    def test_missing_tilt_field_raises(self):
        pattern = compile_template('{}_{position}.mrc')
        with pytest.raises(ValueError):
            extract_tilt_angle('a_b.mrc', pattern)

    def test_custom_delimiters_mix_separators(self):
        pattern = compile_template('{}-{}_{}-{tilt}.mrc', delimiters='_-')
        assert extract_tilt_angle('sample-01_tilt-30.00.mrc', pattern) == pytest.approx(30.00)

    def test_invalid_field_name_raises(self):
        with pytest.raises(ValueError, match='invalid template field name'):
            compile_template('{}_{1invalid}_{tilt}.mrc')

    def test_unparseable_tilt_raises(self):
        pattern = compile_template('{}_{tilt}.mrc')
        with pytest.raises(ValueError, match='could not parse tilt angle'):
            extract_tilt_angle('foo_notanumber.mrc', pattern)