"""Languages: English exactly as it always was, Spanish in full, and choosing between them
(Voice's own setting or Limitless Sound's), with the model downloaded once and offline handled.
No mic, no real OS, no hub, no speech model: a model folder is faked where one's needed."""
import ast
import shutil
import unittest
from pathlib import Path
from unittest import mock

# first: it sets up a private config folder and an offscreen screen
from test_setup import make

# isort: split
from limitless_voice import app as app_module
from limitless_voice.engine import Engine
from limitless_voice.grammar import DEFAULT_PACK_DIR, load_packs
from limitless_voice.keys import spoken_to_chord
from limitless_voice.language import ENGLISH, builtin_packs, load, model_for, wanted
from limitless_voice.platforms.dryrun import DryRunPlatform
from limitless_voice.settings import data_dir
from limitless_voice.suite import Suite
from limitless_voice.voice_out import pick_voice

ES = load("es")
PACKS = {os: load_packs([DEFAULT_PACK_DIR], os) for os in ("mac", "windows")}
SPANISH = {os: ES.translate(p) for os, p in PACKS.items()}


def engine(app="Logic Pro", os_name="mac"):
    p = DryRunPlatform(os_name, app=app)
    return Engine(p, SPANISH[os_name], own_names=["Limitless Voice"], language=ES), p


def pressed(p):
    return [e[1] for e in p.log if e[0] in ("press", "type")]


class English(unittest.TestCase):
    """What Voice listened for in English before it had languages, word for word."""

    def test_its_own_words_are_the_ones_it_always_had(self):
        w = ENGLISH.words
        self.assertEqual(w["wake"], {"wake up", "start listening", "computer wake up"})
        self.assertEqual(w["sleep"], {"go to sleep", "stop listening"})
        self.assertEqual(w["cancel"], {"cancel", "never mind", "nevermind", "no"})
        self.assertEqual(w["yes"], {"yes", "confirm", "do it", "yes please"})
        self.assertEqual(w["again"], {"again", "repeat that", "do that again", "one more time", "same again"})
        self.assertEqual(w["help"], {"what can i say", "show commands", "help"})
        self.assertEqual(w["take_stop"], {"stop", "stop recording", "stop playback", "stop the take"})
        self.assertEqual(ENGLISH.lists["filler_start"],
                         ["please", "um", "uh", "okay", "ok", "hey computer", "computer"])
        self.assertEqual(ENGLISH.lists["filler_end"], ["please", "thanks", "thank you"])

    def test_the_packs_are_untouched(self):
        self.assertIs(ENGLISH.translate(PACKS["mac"]), PACKS["mac"])
        self.assertEqual(ENGLISH.check(), [])
        self.assertEqual(ENGLISH.text("Say yes to {what}, or cancel", what="quit this app"),
                         "Say yes to quit this app, or cancel")

    def test_keys_and_letters(self):
        for said, chord in [("command shift november", "cmd+shift+n"), ("f 5", "f5"), ("close bracket", "]"),
                            ("option command b", "opt+cmd+b"), ("delete", "delete")]:
            self.assertEqual(spoken_to_chord(said), chord, said)


class SpanishFile(unittest.TestCase):
    def test_every_command_in_every_pack_has_spanish(self):
        self.assertEqual(ES.check(builtin_packs()), [])

    def test_the_english_it_stands_for_is_kept(self):
        logic = next(p for p in SPANISH["mac"] if p.name == "Logic Pro")
        play = next(c for c in logic.commands if "reproducir" in c.phrases)
        self.assertEqual(play.english_of("parar"), "stop")
        self.assertEqual(play.english_of("dale play"), "play")
        self.assertEqual(play.english[0], "play")

    def test_numbers(self):
        cases = {"compás treinta y dos": "compás 32", "compás ciento veinte": "compás 120",
                 "compás doscientos treinta y cinco": "compás 235", "tempo ciento veintiocho": "tempo 128",
                 "mil novecientos noventa y nueve": "1999", "dos mil": "2000", "veintiuno": "21",
                 "compás uno dos ocho": "compás 128", "marcador un": "marcador 1", "un compás": "un compás",
                 "rock y roll": "rock y roll", "treinta y": "30 y"}
        for said, want in cases.items():
            self.assertEqual(ES.numbers.normalize(said), want, said)

    def test_keys_and_letters(self):
        for said, chord in [("comando mayúsculas ene", "cmd+shift+n"), ("comando uve doble", "cmd+w"),
                            ("comando doble u", "cmd+w"), ("control efe 5", "ctrl+f5"),
                            ("punto y coma", ";"), ("opción comando be", "opt+cmd+b"), ("comando zeta", "cmd+z")]:
            self.assertEqual(spoken_to_chord(said, ES), chord, said)

    def test_which_language(self):
        self.assertEqual(wanted("", None, ""), "en")              # as Voice always was
        self.assertEqual(wanted("", "es", ""), "es")              # Limitless Sound's
        self.assertEqual(wanted("en", "es", ""), "en")            # chosen in Voice: that one
        self.assertEqual(wanted("", None, "es"), "es")            # the hub's last, while it's not running
        self.assertEqual(wanted("", "es-MX", ""), "es")
        self.assertEqual(wanted("", "fr", "es"), "en")            # not one Voice has: English
        self.assertEqual(model_for(ES, "vosk-model-small-en-us-0.15"), "vosk-model-small-es-0.42")
        self.assertEqual(model_for(ENGLISH, "vosk-model-small-en-in-0.4"), "vosk-model-small-en-in-0.4")

    def test_every_text_voice_shows_or_says_has_spanish(self):
        """Every reply, status and help line in the code (lang.text, _reply), and every state the
        floating display names, is in the Spanish file."""
        found = texts_in_code()
        self.assertGreater(len(found), 60)
        self.assertEqual(sorted(t for t in found if t not in ES.texts), [])


def texts_in_code():
    """Every reply, status and help line in Voice's code (lang.text, _reply), and every state the
    floating display names: what a language's texts must have."""
    found = set()

    def strings(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value
        elif isinstance(node, ast.IfExp):
            yield from strings(node.body)
            yield from strings(node.orelse)
        elif isinstance(node, ast.Subscript):
            yield from strings(node.value)
        elif isinstance(node, ast.Dict):
            for v in node.values:
                yield from strings(v)

    for path in Path(app_module.__file__).parent.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.args:
                if node.func.attr == "text":
                    found.update(strings(node.args[0]))
                elif node.func.attr == "_reply" and len(node.args) > 1:
                    found.update(strings(node.args[1]))
    from limitless_voice.hud import STATES
    found.update(label for _, label in STATES.values())
    return found


class SpanishEngine(unittest.TestCase):
    def test_commands(self):
        cases = [
            ("Logic Pro", "ir al compás treinta y dos", ["/", "32", "return"]),
            ("Pro Tools", "compás ciento veintiocho", ["numpad*", "128", "return"]),
            ("Pro Tools", "desplazar a la derecha cuatro veces", ["numpad+"] * 4),
            ("Logic Pro", "pulsa comando mayúsculas ene", ["cmd+shift+n"]),
            ("Logic Pro", "reproducir", ["space"]),
            ("Logic Pro", "dale play", ["space"]),
            ("Pro Tools", "parar", ["space"]),
            ("Logic Pro", "grabar", ["r"]),
            ("Logic Pro", "por favor guarda el proyecto gracias", ["cmd+s"]),
            ("Logic Pro", "mostrar el mezclador", ["x"]),
            ("Logic Pro", "silenciar la pista", ["m"]),
            ("Logic Pro", "mute", ["m"]),
            ("Ableton Live", "nueva pista midi", ["cmd+shift+t"]),
            ("Ableton Live", "ir al compás treinta y dos", []),   # Live has no key for it
            ("Logic Pro", "loop", ["c"]),
            ("Pro Tools", "loop", ["shift+cmd+l"]),
            ("Logic Pro", "flecha arriba", ["up"]),
            ("Finder", "deshacer", ["cmd+z"]),
            ("Logic Pro", "arriba", []),                 # said all the time, so not alone
            ("Logic Pro", "este solo de guitarra", []),
        ]
        for app, said, keys in cases:
            e, p = engine(app)
            e.handle(said, said)
            self.assertEqual(pressed(p), keys, f"{said} in {app}")

    def test_a_daw_command_with_no_daw_in_front_says_why_in_spanish(self):
        e, _ = engine("Finder")
        r = e.handle("reproducir", "reproducir")
        self.assertFalse(r.handled)
        self.assertEqual(r.message, '"reproducir" funciona en Ableton Live, Logic Pro y Pro Tools. '
                                    "Pon uno de ellos al frente y dilo otra vez.")

    def test_yes_and_cancel(self):
        e, p = engine()
        r = e.handle("salir de la aplicación", "salir de la aplicación")
        self.assertEqual((r.kind, r.message), ("ask", "Di sí para salir de esta aplicación, o cancela"))
        self.assertEqual(e.handle("cancelar").message, "Cancelado")
        e.handle("cierra la ventana", "cierra la ventana")
        e.handle("sí", "sí")
        self.assertEqual(pressed(p), ["cmd+w"])

    def test_a_cut_not_heard_twice_asks_first(self):
        e, p = engine()
        r = e.handle("cortar", "portal")         # the open recognizer heard another word
        self.assertEqual(r.kind, "ask")
        self.assertEqual(pressed(p), [])
        e.handle("sí", "sí")
        self.assertEqual(pressed(p), ["cmd+x"])
        e, p = engine()
        e.handle("borrar cincuenta veces", "borrar cincuenta veces")
        self.assertEqual(pressed(p), ["delete"] * 3)   # never more than three at once

    def test_destructive_commands_alone_are_infinitives(self):
        """People's "corte" and "corto" came back as "corta" from both recognizers."""
        for said in ("corta", "pega", "borra", "elimina", "duplica"):
            for app in ("Logic Pro", "Pro Tools"):
                e, p = engine(app)
                e.handle(said, said)
                self.assertEqual(pressed(p), [], f"{said} in {app}")

    def test_free_text_needs_the_open_recognizer_too(self):
        """A sentence can come back all in command words ("de", "la", "al"): then the free text is
        the open recognizer's, or nothing happens."""
        e, p = engine()
        r = e.handle("abrir te garage de al ir al en ese punto", "advierte que nadie puede dar garantía")
        self.assertFalse(r.handled)
        self.assertEqual(p.log, [])
        e.handle("abre logic", "abre logic")
        self.assertEqual([x for x in p.log if x[0] == "open"], [("open", "Logic Pro")])

    def test_sleep_wake_help_again(self):
        e, p = engine()
        self.assertEqual(e.handle("a dormir").message, "Dejo de escuchar")
        self.assertFalse(e.handle("grabar").handled)
        self.assertEqual(e.handle("despierta").message, "Escuchando")
        r = e.handle("qué puedo decir")
        self.assertEqual(r.kind, "help")
        self.assertTrue(r.message.startswith("Comandos para Logic Pro:"))
        self.assertEqual(e.handle("otra vez").message, "Todavía no hay nada que repetir")
        e.handle("siguiente pista")
        e.handle("otra vez")
        self.assertEqual(pressed(p), ["down", "down"])

    def test_take_mode(self):
        e, p = engine()
        e.take = True
        for lyric in ("solo", "silenciar", "deshacer", "guardar"):
            self.assertEqual(e.handle(lyric).message, "take")
        r = e.handle("parar")
        self.assertTrue(r.handled)
        self.assertEqual((pressed(p), r.english), (["space"], "stop"))

    def test_dictation(self):
        e, p = engine()
        e.handle("empezar dictado")
        e.handle("hola coma qué tal signo de interrogación", "hola coma qué tal signo de interrogación")
        e.handle("nueva línea")
        r = e.handle("borra eso")
        self.assertEqual(r.message, "Borrado")
        self.assertEqual(e.handle("terminar dictado").message, "De vuelta a los comandos")
        self.assertFalse(e.dictating)
        self.assertEqual([x[1] for x in p.log if x[0] == "type"], [" hola, qué tal?"])

    def test_the_suite_hears_it_in_english(self):
        e, p = engine()
        s = Suite(e)
        s.link = mock.Mock()
        r = e.handle("parar", "parar")
        s.report(r)
        s.link.did.assert_called_with("stop", "daw.stop")
        e.handle("solo pista", "solo pista")
        ok, message = s.invoke("play", {}, "gaze")                 # an intent, from another app
        self.assertTrue(ok)
        ok, message = s.invoke("do", {"phrase": "go to bar thirty two"}, "x")   # the suite talks English
        self.assertEqual((ok, message), (True, "Compás 32"))
        ok, message = s.invoke("do", {"phrase": "ir al compás ocho"}, "x")      # or Voice's own words
        self.assertEqual((ok, message), (True, "Compás 8"))
        ok, message = s.invoke("do", {"phrase": "quit the app"}, "x")
        self.assertEqual(message, "Ese comando necesita que digas sí, así que no se puede usar desde otra "
                                  "aplicación.")
        self.assertEqual(pressed(p), ["space", "s", "space", "/", "32", "return", "/", "8", "return"])
        e, _ = engine("Finder")
        s = Suite(e)
        s.link = mock.Mock()
        self.assertEqual(s.invoke("solo", {}, "x"),
                         (False, "Solo funciona cuando Logic Pro o Pro Tools está al frente."))
        s.language = "es"
        s.report_look({"textScale": 1.0})
        s.link.state.assert_called_with("prefs.applied", {"textScale": 1.0, "language": "es"})


class Voices(unittest.TestCase):
    def test_a_voice_for_the_language(self):
        mac = [("Alex", "en_US"), ("Eddy (Spanish (Mexico))", "es_MX"), ("Paulina (Enhanced)", "es_MX"),
               ("Jorge", "es_ES")]
        self.assertEqual(pick_voice(ES, mac), "Paulina (Enhanced)")     # a favourite first
        self.assertEqual(pick_voice(ES, mac[:2]), "Eddy (Spanish (Mexico))")
        self.assertIsNone(pick_voice(ES, [("Alex", "en_US"), ("Thomas", "fr_FR")]))
        self.assertIsNone(pick_voice(ENGLISH, mac))                     # English: the computer's own
        windows = [("HKEY\\TTS_MS_EN-US_ZIRA_11.0", "HKEY\\TTS_MS_EN-US_ZIRA_11.0 Microsoft Zira Desktop - English"),
                   ("HKEY\\TTS_MS_ES-MX_SABINA_11.0",
                    "HKEY\\TTS_MS_ES-MX_SABINA_11.0 Microsoft Sabina Desktop - Spanish (Mexico)")]
        self.assertEqual(pick_voice(ES, windows), "HKEY\\TTS_MS_ES-MX_SABINA_11.0")


PT = load("pt")
PORTUGUESE = {os: PT.translate(p) for os, p in PACKS.items()}


def pt_engine(app="Logic Pro", os_name="mac"):
    p = DryRunPlatform(os_name, app=app)
    return Engine(p, PORTUGUESE[os_name], own_names=["Limitless Voice"], language=PT), p


class PortugueseFile(unittest.TestCase):
    """Brazilian Portuguese: every command, numbers with "um" and "uma" that are also the article,
    keys and letters, and every text."""

    def test_every_command_in_every_pack_has_portuguese(self):
        self.assertEqual(PT.check(builtin_packs()), [])

    def test_every_text_voice_shows_or_says_has_portuguese(self):
        self.assertEqual(sorted(t for t in texts_in_code() if t not in PT.texts), [])
        self.assertEqual(sorted(PT.texts), sorted(ES.texts))

    def test_the_english_it_stands_for_is_kept(self):
        logic = next(p for p in PORTUGUESE["mac"] if p.name == "Logic Pro")
        play = next(c for c in logic.commands if "tocar" in c.phrases)
        self.assertEqual(play.english_of("parar"), "stop")
        self.assertEqual(play.english_of("reproduzir"), "play")
        self.assertEqual(play.english_of("parar a reprodução"), "stop playback")

    def test_english_names_spelled_as_words_the_model_knows(self):
        """The small Portuguese model doesn't know "mute", "loop" or "mixer": it hears "mi ute",
        "lupi" and "mix ser", which are written back as the English names."""
        from limitless_voice.engine import normalize
        packs = PORTUGUESE["mac"]
        phrases = PT.recognizer_phrases(packs)
        for heard, said in [("mi ute", "mute"), ("lupi", "loop"), ("mostrar o mix ser", "mostrar o mixer"),
                            ("piano rol", "piano roll"), ("sair do modo tei que", "sair do modo take"),
                            ("quantia azar", "quantizar")]:
            self.assertIn(heard, phrases)
            self.assertEqual(normalize(heard, PT), said)

    def test_numbers(self):
        cases = {"compasso trinta e dois": "compasso 32", "compasso cento e vinte e oito": "compasso 128",
                 "compasso duzentos e trinta e cinco": "compasso 235", "tempo cento e vinte": "tempo 120",
                 "mil novecentos e noventa e nove": "1999", "dois mil": "2000", "mil e quinhentos": "1500",
                 "vinte e um": "21", "compasso um dois oito": "compasso 128", "compasso cem": "compasso 100",
                 "marcador um": "marcador 1", "compasso um meia": "compasso 16", "duas vezes": "2 vezes",
                 # the article, not 1
                 "adicionar uma faixa": "adicionar uma faixa", "avançar um compasso": "avançar um compasso",
                 "mais uma vez": "mais uma vez", "rock e roll": "rock e roll", "trinta e": "30 e"}
        for said, want in cases.items():
            self.assertEqual(PT.numbers.normalize(said), want, said)

    def test_keys_and_letters(self):
        for said, chord in [("comando maiúsculas n", "cmd+shift+n"), ("comando maiúsculas novembro", "cmd+shift+n"),
                            ("comando uísque", "cmd+w"), ("control f 5", "ctrl+f5"), ("ponto e vírgula", ";"),
                            ("opção comando bê", "opt+cmd+b"), ("comando zê", "cmd+z"), ("comando e", "cmd+e"),
                            ("comando para cima", "cmd+up")]:
            self.assertEqual(spoken_to_chord(said, PT), chord, said)

    def test_which_language(self):
        self.assertEqual(wanted("", "pt-BR", ""), "pt")
        self.assertEqual(wanted("", "pt_PT", ""), "pt")
        self.assertEqual(wanted("es", "pt", ""), "es")
        self.assertEqual(model_for(PT, "vosk-model-small-es-0.42"), "vosk-model-small-pt-0.3")


class PortugueseEngine(unittest.TestCase):
    def test_commands(self):
        cases = [
            ("Logic Pro", "ir para o compasso trinta e dois", ["/", "32", "return"]),
            ("Pro Tools", "compasso cento e vinte e oito", ["numpad*", "128", "return"]),
            ("Pro Tools", "deslocar para a direita quatro vezes", ["numpad+"] * 4),
            ("Pro Tools", "deslocar para a direita duas vezes", ["numpad+"] * 2),
            ("Pro Tools", "marcador um", ["numpad.", "1", "numpad."]),
            ("Logic Pro", "aperte comando maiúsculas n", ["cmd+shift+n"]),
            ("Logic Pro", "tocar", ["space"]),
            ("Logic Pro", "reproduzir", ["space"]),
            ("Pro Tools", "parar", ["space"]),
            ("Logic Pro", "gravar", ["r"]),
            ("Logic Pro", "por favor salva o projeto obrigado", ["cmd+s"]),
            ("Logic Pro", "mostrar o mixer", ["x"]),
            ("Logic Pro", "muta a faixa", ["m"]),
            ("Logic Pro", "mi ute", ["m"]),
            ("Logic Pro", "solo", ["s"]),
            ("Logic Pro", "clique", ["k"]),
            ("Logic Pro", "lupi", ["c"]),
            ("Logic Pro", "pare", ["space"]),
            ("Logic Pro", "sala", []),                   # a letter from "salva", but another word
            ("Logic Pro", "parte", []),
            ("Logic Pro", "salva", []),                  # "sala" came back as it
            ("Logic Pro", "toca", []),                   # said alone, a command is the infinitive
            ("Logic Pro", "volta", []),
            ("Logic Pro", "para", ["space"]),            # how Brazilians say stop
            ("Logic Pro", "toca a partir daqui", []),
            ("Logic Pro", "silencia a faixa", ["m"]),
            ("Logic Pro", "muta", []),                   # and "muita" as this
            ("Logic Pro", "arma", []),                   # a weapon
            ("Logic Pro", "salva o projeto", ["cmd+s"]),
            ("Logic Pro", "arma a faixa", ["ctrl+r"]),
            ("Logic Pro", "adicionar uma faixa", ["opt+cmd+n"]),
            ("Logic Pro", "avançar um compasso", ["."]),
            ("Ableton Live", "nova faixa midi", ["cmd+shift+t"]),
            ("Ableton Live", "ir para o compasso trinta e dois", []),   # Live has no key for it
            ("Logic Pro", "loop", ["c"]),
            ("Pro Tools", "loop", ["shift+cmd+l"]),
            ("Logic Pro", "seta para cima", ["up"]),
            ("Finder", "desfazer", ["cmd+z"]),
            ("Logic Pro", "cima", []),                   # said all the time, so not alone
            ("Logic Pro", "esse solo de guitarra", []),
        ]
        for app, said, keys in cases:
            e, p = pt_engine(app)
            e.handle(said, said)
            self.assertEqual(pressed(p), keys, f"{said} in {app}")

    def test_a_sentence_without_the_command_is_talk(self):
        """When the open recognizer heard two words or more, and not the command recognizer's
        first, someone was talking: a reader's "quando você liga para alguém que" was "parar"."""
        for heard, open_, keys in [("parar", "quando você liga para alguém que", []),
                                   ("solo", "polo químicas", []),
                                   ("dividir", "o que alguns casos", []),
                                   ("para", "e acampamento para famílias com", []),
                                   ("para", "se para se", []),                    # two more words
                                   ("para", "para o", ["space"]),
                                   ("parar", "parar", ["space"]), ("parar", "", ["space"]),
                                   ("parar", "pare", ["space"]),            # one word: could be it
                                   ("tocar", "tocar agora", ["space"]),     # the command is in it
                                   ("mi ute", "mi ute", ["m"]),
                                   ("ir para o compasso trinta e dois", "ir para o compasso trinta e dois",
                                    ["/", "32", "return"])]:
            e, p = pt_engine()
            e.handle(heard, open_)
            self.assertEqual(pressed(p), keys, f"{heard} / {open_}")
        e, p = pt_engine()
        e.handle("começar ditado", "começar ditado")
        e.handle("parar ditado", "para o ditado agora")     # Voice's own words aren't affected
        self.assertFalse(e.dictating)

    def test_destructive_commands_alone_are_infinitives_and_exact(self):
        """"corta", "cola" and "apaga" are Cut, Paste and Delete only with "isso" after them, and a
        word a letter away ("pagar", "colou") never throws work away."""
        for said in ("corta", "recorta", "cola", "apaga", "exclui", "deleta", "duplica", "pagar", "colou",
                     "cortou", "apagou", "colagem", "duplicado"):
            for app in ("Logic Pro", "Pro Tools", "Ableton Live"):
                e, p = pt_engine(app)
                e.handle(said, said)
                self.assertEqual(pressed(p), [], f"{said} in {app}")
        for said, keys in [("recortar", ["cmd+x"]), ("colar", ["cmd+v"]), ("apagar", ["delete"]),
                           ("excluir isso", ["delete"]), ("corta isso", ["cmd+x"])]:
            e, p = pt_engine()
            e.handle(said, said)
            self.assertEqual(pressed(p), keys, said)

    def test_a_cut_not_heard_twice_asks_first(self):
        e, p = pt_engine()
        r = e.handle("recortar", "recordar")      # the open recognizer heard another word
        self.assertEqual((r.kind, r.message), ("ask", "Diga sim para recortar, ou cancele"))
        e.handle("sim", "sim")
        self.assertEqual(pressed(p), ["cmd+x"])
        e, p = pt_engine()
        e.handle("apagar cinquenta vezes", "apagar cinquenta vezes")
        self.assertEqual(pressed(p), ["delete"] * 3)   # never more than three at once

    def test_free_text_needs_the_open_recognizer_too(self):
        e, p = pt_engine()
        r = e.handle("abrir a faixa de o compasso", "a bruxa da floresta escura")
        self.assertFalse(r.handled)
        self.assertEqual(p.log, [])
        e.handle("abrir logic", "abrir logic")
        self.assertEqual([x for x in p.log if x[0] == "open"], [("open", "Logic Pro")])

    def test_yes_cancel_sleep_wake_help_again(self):
        e, p = pt_engine()
        r = e.handle("sair do aplicativo", "sair do aplicativo")
        self.assertEqual((r.kind, r.message), ("ask", "Diga sim para sair deste aplicativo, ou cancele"))
        self.assertEqual(e.handle("cancelar").message, "Cancelado")
        self.assertEqual(e.handle("vai dormir").message, "Parei de ouvir")
        self.assertFalse(e.handle("gravar").handled)
        self.assertEqual(e.handle("acorda").message, "Ouvindo")
        r = e.handle("o que eu posso dizer")
        self.assertEqual(r.kind, "help")
        self.assertTrue(r.message.startswith("Comandos para Logic Pro:"))
        self.assertEqual(e.handle("de novo").message, "Ainda não há nada para repetir")
        e.handle("próxima faixa")
        e.handle("de novo")
        self.assertEqual(pressed(p), ["down", "down"])

    def test_take_mode(self):
        e, p = pt_engine()
        e.take = True
        for lyric in ("solo", "silenciar", "desfazer", "salvar", "tocar"):
            self.assertEqual(e.handle(lyric).message, "take")
        r = e.handle("parar")
        self.assertTrue(r.handled)
        self.assertEqual((pressed(p), r.english), (["space"], "stop"))
        e.take = True
        self.assertEqual(e.handle("pare").english, "stop")

    def test_dictation(self):
        e, p = pt_engine()
        e.handle("começar ditado")
        e.handle("olá vírgula tudo bem ponto de interrogação", "olá vírgula tudo bem ponto de interrogação")
        e.handle("nova linha")
        self.assertEqual(e.handle("apaga isso").message, "Apagado")
        self.assertEqual(e.handle("parar ditado").message, "De volta aos comandos")
        self.assertEqual([x[1] for x in p.log if x[0] == "type"], [" olá, tudo bem?"])

    def test_the_suite_hears_it_in_english(self):
        e, p = pt_engine()
        s = Suite(e)
        s.link = mock.Mock()
        s.report(e.handle("parar", "parar"))
        s.link.did.assert_called_with("stop", "daw.stop")
        ok, message = s.invoke("do", {"phrase": "go to bar thirty two"}, "x")   # the suite talks English
        self.assertEqual((ok, message), (True, "Compasso 32"))
        ok, message = s.invoke("do", {"phrase": "ir para o compasso oito"}, "x")
        self.assertEqual((ok, message), (True, "Compasso 8"))
        self.assertEqual(e.from_english("go to bar 32"), "ir para o compasso 32")
        self.assertEqual(e.from_english("nudge right 4 times", everywhere=True), "deslocar para a direita 4 vezes")
        self.assertEqual(pressed(p), ["space", "/", "32", "return", "/", "8", "return"])

    def test_a_brazilian_voice_first(self):
        mac = [("Alex", "en_US"), ("Joana", "pt_PT"), ("Luciana (Enhanced)", "pt_BR")]
        self.assertEqual(pick_voice(PT, mac), "Luciana (Enhanced)")
        self.assertEqual(pick_voice(PT, mac[:2]), "Joana")
        windows = [("HKEY\\TTS_MS_PT-BR_MARIA_11.0",
                    "HKEY\\TTS_MS_PT-BR_MARIA_11.0 Microsoft Maria Desktop - Portuguese(Brazil)")]
        self.assertEqual(pick_voice(PT, windows), "HKEY\\TTS_MS_PT-BR_MARIA_11.0")


HUB_PREFS = {"speak": True, "oneVoice": True, "textScale": 1.0, "highContrast": False, "reduceMotion": False}


class ChoosingTheLanguage(unittest.TestCase):
    """The window, its Settings and the hub's shared language, through the real link."""

    def setUp(self):
        self.w, self.p, self.s = make(mic="granted", control=True)
        self.sent = []
        link = self.w.suite.link
        link._send = lambda msg: link.connected and (self.sent.append(msg) or True)
        self.model = data_dir() / "models" / "vosk-model-small-es-0.42"

    def tearDown(self):
        shutil.rmtree(self.model, ignore_errors=True)
        self.w.shutdown()
        self.w.deleteLater()

    def hub(self, op="prefs", **prefs):
        self.w.suite.link._handle({"op": op, "prefs": {**HUB_PREFS, **prefs}})

    def applied(self):
        return [m["value"]["language"] for m in self.sent if m.get("op") == "state" and m["key"] == "prefs.applied"]

    def download(self):
        (self.model / "conf").mkdir(parents=True, exist_ok=True)

    def test_english_until_asked(self):
        w = self.w
        self.hub("welcome")
        self.assertEqual((w.lang.code, w.engine.lang.code), ("en", "en"))
        self.assertTrue(w.language_box.isHidden())
        self.assertEqual(w.listen_btn.text(), 'Listening: say "go to sleep" to pause')
        self.assertEqual(self.applied(), ["en"])

    def test_the_suites_language_without_its_model_offers_the_download(self):
        w = self.w
        self.hub("welcome", language="es")
        self.assertEqual(w.lang.code, "en")                     # keeps listening in what it has
        self.assertFalse(w.language_box.isHidden())
        self.assertIn("necesita descargar su modelo de voz (39 MB)", w.language_text.text())
        self.assertEqual(w.language_download.text(), "Descargar español (39 MB)")
        self.assertEqual(self.applied(), ["en"])                 # so the hub reads it in English
        self.assertEqual(self.s.extra["suite_language"], "es")   # and next time starts in it
        from test_accessibility import problems, tab_stops
        self.assertEqual(problems(w), [])
        self.assertIn(w.language_download, tab_stops(w))        # the keyboard reaches it

    def test_the_suites_portuguese_offers_its_download_and_then_listens_in_it(self):
        w = self.w
        self.hub("welcome", language="pt")
        self.assertEqual(w.lang.code, "en")
        self.assertEqual(w.language_download.text(), "Baixar português (31 MB)")
        self.assertIn("precisa baixar o modelo de voz (31 MB)", w.language_text.text())
        model = data_dir() / "models" / "vosk-model-small-pt-0.3"
        self.addCleanup(shutil.rmtree, model, True)

        def download(*a, **k):
            # laid out as the real one: everything in one folder, no am/ or conf/
            model.mkdir(parents=True)
            (model / "final.mdl").write_bytes(b"")
            return model

        with mock.patch.object(app_module, "ensure_model", side_effect=download):
            w.language_download.click()
        self.assertEqual(app_module.find_model("vosk-model-small-pt-0.3"), model)   # found next time too
        self.assertEqual((w.lang.code, w.engine.lang.code), ("pt", "pt"))
        self.assertEqual(w.listen_btn.text(), 'Ouvindo: diga "vai dormir" para pausar')
        self.assertEqual(self.applied(), ["en", "pt"])
        self.assertIn("Ouvindo em português", w.speaker.said)

    def test_offline_the_offer_stays(self):
        w = self.w
        self.hub("welcome", language="es")
        with mock.patch.object(app_module, "ensure_model", return_value=None) as ensure:   # couldn't download
            w.language_download.click()
        ensure.assert_called_once()
        self.assertEqual(w.lang.code, "en")
        self.assertFalse(w.language_box.isHidden())

    def test_once_downloaded_it_listens_and_answers_in_spanish(self):
        w = self.w
        self.hub("welcome", language="es")
        with mock.patch.object(app_module, "ensure_model", side_effect=lambda *a, **k: self.download() or self.model) \
                as ensure:
            w.language_download.click()
        self.assertEqual(ensure.call_args.kwargs, {"ask": False})   # pressing Download was the yes
        self.assertEqual((w.lang.code, w.engine.lang.code), ("es", "es"))
        self.assertEqual(w.listener.model_path, self.model)
        self.assertTrue(w.language_box.isHidden())
        self.assertEqual(w.listen_btn.text(), 'Escuchando: di "a dormir" para hacer una pausa')
        self.assertEqual(self.applied(), ["en", "es"])
        self.assertIn("Escuchando en español", w.speaker.said)
        w.on_heard("ir al compás doce", "ir al compás doce")
        self.assertEqual([x[1] for x in self.p.log if x[0] in ("press", "type")][-3:],
                         ["numpad*", "12", "return"])   # Pro Tools is in front
        self.assertEqual(w.heard_label.text(), "Oído: “ir al compás 12”")
        english = data_dir() / "models" / "vosk-model-small-en-us-0.15"
        (english / "conf").mkdir(parents=True)
        self.addCleanup(shutil.rmtree, english)
        self.hub(language="en")                                  # the suite back to English
        self.assertEqual((w.lang.code, self.applied()[-1]), ("en", "en"))

    def test_voices_own_choice_wins(self):
        w = self.w
        self.download()
        self.s.language = "en"
        self.hub("welcome", language="es")
        self.assertEqual(w.lang.code, "en")
        self.s.language = "es"
        w.apply_language()
        self.assertEqual(w.lang.code, "es")

    def test_settings_can_choose_it_and_say_its_a_download(self):
        from test_accessibility import problems
        w = self.w
        dialog = app_module.SettingsDialog(w, self.s, w.suite_language())
        items = [dialog.language.itemText(i) for i in range(dialog.language.count())]
        self.assertEqual(items, ["Same as Limitless Sound (English)", "English (40 MB download)",
                                 "Español (39 MB download)", "Português (prévia) (31 MB download)"])
        dialog.language.setCurrentIndex(dialog.language.findData("pt"))   # a preview says so first
        self.assertTrue(dialog.language_note.text().startswith("Prévia: em português, o Limitless Voice entende "
                                                               "cerca de 6 em cada 10 comandos"))
        self.assertTrue(dialog.language_note.text().endswith("O português é baixado uma vez (31 MB) e depois "
                                                             "funciona sem internet."))
        dialog.language.setCurrentIndex(dialog.language.findData("es"))
        self.assertEqual(dialog.model.itemData(0), "vosk-model-small-es-0.42")
        self.assertEqual(dialog.language_note.text(),
                         "El español se descarga una vez (39 MB) y luego funciona sin internet.")
        self.assertEqual(problems(dialog), [])
        dialog.apply()
        self.assertEqual(self.s.language, "es")
        dialog.reject()

    def test_no_spanish_voice_says_where_to_add_one(self):
        w = self.w
        self.download()
        self.hub("welcome", language="es")
        w._no_voice(ES)
        self.assertFalse(w.language_box.isHidden())
        self.assertTrue(w.language_download.isHidden())
        self.assertIn("no tiene una voz en español", w.language_text.text())


if __name__ == "__main__":
    unittest.main()
