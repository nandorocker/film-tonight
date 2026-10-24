import unittest
from pathlib import Path
from providers_html import _edison_languages,parse_kino35
from providers import classify

class LanguageRegressionTests(unittest.TestCase):
    def test_edison_unsupported_mixed_audio_is_not_trailing_english(self):
        for raw in ['FR + EN, Sub. CZ','Festival FR & EN, Sub. CZ','Festival FR; EN, Sub. CZ','Festival FR and EN, Sub. CZ']:
            audio,subs=_edison_languages(raw)
            self.assertEqual(audio,[],raw)
            self.assertEqual(classify(audio,subs),'unknown',raw)

    def test_kino35_combined_icons_preserve_individual_codes(self):
        source=(Path(__file__).parent/'fixtures/html/kino35.html').read_text().replace('>FR</div>','>FR, EN</div>').replace('>EN</div>','>CS, EN</div>')
        _,rows=parse_kino35(source,{'id':'35','url':'https://kino35.ifp.cz/'},'2026-10-24')
        self.assertEqual(rows[0]['audio'],['fr','en'])
        self.assertEqual(rows[0]['subtitles'],['cs','en'])
        self.assertEqual(rows[0]['access'],'english_subtitles')
        source=source.replace('>CS, EN</div>','>CS</div>')
        _,rows=parse_kino35(source,{'id':'35','url':'https://kino35.ifp.cz/'},'2026-10-24')
        self.assertEqual(rows[0]['access'],'unknown')

if __name__=='__main__':unittest.main()
