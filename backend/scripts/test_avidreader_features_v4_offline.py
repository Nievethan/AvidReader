"""Offline checks for the v4 normalization logic (no Cloudflare request)."""
import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name('test_avidreader_features_v4.py')
spec = importlib.util.spec_from_file_location('avidreader_v4', SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class OfflineTests(unittest.TestCase):
    def test_story_mentions_override_incomplete_model_list(self):
        result = mod.normalize('what_if', {'story': 'Mira and Elias sailed together.',
                                          'characters_involved': ['Mira']})
        self.assertEqual(result['characters_involved'], ['Mira', 'Elias'])

    def test_story_mentions_do_not_include_unmentioned_characters(self):
        result = mod.normalize('story_continues', {'story': 'Mira waited alone.',
                                                'characters_involved': ['Elias']})
        self.assertEqual(result['characters_involved'], ['Mira'])

    def test_word_wall_finds_exact_source_sentence(self):
        result = mod.normalize('word_wall', {'entries': [
            {'word': 'forbidden', 'meaning_in_context': 'not allowed', 'source_quote': None}]})
        self.assertIn('forbidden island', result['entries'][0]['source_quote'])
        self.assertIn(result['entries'][0]['source_quote'], mod.PASSAGE)

    def test_environment_omits_hallucinated_description(self):
        result = mod.normalize('environment', {'locations': [
            {'name': 'beach', 'description': 'The lighthouse is on the beach.',
             'evidence_quote': 'Elias found a brass compass on the beach.'}]})
        self.assertEqual(len(result['locations']), 1)
        location = result['locations'][0]
        self.assertNotIn('lighthouse', location['description'].lower())
        self.assertIn(location['description'], mod.PASSAGE)

    def test_environment_skips_unsupported_location(self):
        with self.assertRaises(ValueError):
            mod.normalize('environment', {'locations': [
                {'name': 'castle', 'description': 'A distant castle',
                 'evidence_quote': 'The castle was huge.'}]})

    def test_character_map_keeps_supported_edge(self):
        raw = {'characters': [{'name':'Mira'}, {'name':'Elias'}], 'relationships': [
            {'source':'Mira','target':'Elias','relationship':'friend',
             'evidence':'Her closest friend, Elias'}]}
        data = mod.normalize('character_map', raw)
        self.assertEqual(len(data['nodes']),2)
        self.assertEqual(len(data['edges']),1)

if __name__ == '__main__':
    unittest.main()
