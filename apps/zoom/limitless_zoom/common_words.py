"""Words said all the time, which Zoom listens for only so that its recognizer can write them
down. Said alone they do nothing; said around a command, the command isn't one.

Spanish needs them. With only Zoom's phrases to choose from, the Spanish speech model writes
down a stretch of talk as the command it sounds most like, with no "[unk]" around it: an hour
of people reading aloud (FLEURS) zoomed 76 times. With these 325 words to choose from too, it
zoomed once, and real people's commands were still heard (stress/README.md, "Zoom in Spanish").
English doesn't need them: its model writes such talk down as "[unk]".

SPANISH: the one- and two-letter words ("de", "la", "y"), then the 300 words said most often in
Common Voice's Spanish (the Multilingual Spoken Words Corpus's word counts, which leave out
words shorter than three letters), in that order. Not words that sound like a one-word command
("cerca" and "acercar", "amplia" and "ampliar"): those took commands people said, as well as
the words (a third of the commands, with every such word; stress/test_zoom_real_speech.py
measures the lists tried). Every word is one the speech model knows (test_zoom_language.py).
"""

SPANISH = """
    de la el en y a se un es al lo no su le me mi ha si o e ya te tu yo ni los del que por una
    las con fue como para más sus dos son este esta está tres tiene era sin uno muy pero
    encuentra durante ser entre parte cuatro ciudad fueron hay sobre desde además años seis
    puede actualmente siete nombre todo embargo ocho cinco año esto cuando gran nueve sido
    primera hasta mismo todos ese estos forma universidad primer cada han otros donde tiempo
    entonces están vida ella así estas mayor varios san bien luego vez algunos tuvo tras lugar
    pueden nacional tarde familia cero estaba equipo hijo tanto tienen color varias nueva nació
    historia estado grupo día padre había mundo muchos guerra solo cuenta principal carrera
    centro otras allí poco club obra antes hace sede bajo general todas siempre estudió algunas
    canción segunda sur ellos final posteriormente otro mejor sólo río siguiente españa partido
    película álbum música ambos nunca eso serie eran estudios veces país casa mucho norte aunque
    tenía muchas grandes nada diferentes trabajo otra estados zona ahora nuevo escuela hijos
    hacia obras importante agua esa hoy banda iglesia hizo unidos momento hacer capital junto
    toda finalmente comenzó madre nos sistema dentro mayoría provincia central segundo
    encuentran gobierno siendo menos contra pueblo miembro último estuvo temporada recibió
    presidente vamos región qué hecho tipo muerte mientras fútbol juan trata casi algo isla
    principalmente existen misma estilo especie internacional canciones juego ver ello aquí
    edificio municipio planta noche medio quien primeros madrid debe argentina realizó
    principales director título posee tener según número conocido origen actualidad les maría
    debido largo condado mar actual flores producción porque europa hombre caso derecho programa
    tierra natural vale presenta trabajó hija política personas tan real santa manera estación
    división hermano días teatro igual libro cabeza museo juega base disco televisión población
    países aún francia arte interior unos grande llegó blanco cuerpo niña pasó
""".split()
