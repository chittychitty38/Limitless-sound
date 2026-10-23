"""Bigger lists of words tried as Zoom's Spanish "others", measured by test_zoom_real_speech.py's
variants against the 325 common words the app listens for (limitless_zoom/common_words.py).

NEAR: words at least 72% like a one-word command (difflib's ratio), said at least 5 times in
      MSWC's Spanish: "cerca" and "acercar", "reducido" and "reducir". With every one listened
      for, a third of the commands people said were lost: their confidence fell, or a
      neighbour was heard instead.
TOP1000: MSWC's 1000 most said Spanish words (from Common Voice), three letters or more,
      English words and a few names left out. The app's list is the first 300 of these.
"""

NEAR = """
    abeja acelerar acera acerca acercaba acercan acercarnos acercarse acercó acertar aguantar
    ajustado ajustados ajustan ajustaron ajuste aldea aleja alejaba alejada alejado alejan
    alejaos alejaron alejarse alejaré alejo alejé alejó alero aleta alimenta alimentar
    alimentaria alimentario alimentarse alojar altar alterar amar ambienta amparo amplia
    ampliada ampliado ampliando ampliaron amplias amplificador amplio amplió amplía aplica
    aplicar aplicaron aplicarse argumental asta asustarse atar aumenta aumentaba aumentaban
    aumentado aumentan aumentando aumentaron aumento aumentó bajar calentar calleja causar cera
    cerca cerrar comentar comerciar deducir dejar descubierta descubiertas desespera desierta
    desierto desiertos despertado despertador despertando despertar despertares despertarte
    despertó despide despiertas despiertes despierto despliega diminutivo dimitir disminución
    disminuido disminuye disminuyen disminuyeron disminuyó distinguir distinguió distribuir
    documentar educar elite emite espera esperad esperan esperar esperas espiral espiritual
    experta familiar fomentar gustar justa justas lamentar luna manejar marcar producir
    producirá recipiente reducción reduce reducida reducidas reducido reducidos reducirse remite
    rendir renunciar reparte repente repiten repitiendo repitió repito reproducir reproducirse
    resiste respira resucitar reunir seducir traducir usar valer
""".split()

TOP1000 = """
    los del que por una las con fue como para más sus dos son este esta está tres tiene era sin
    uno muy pero encuentra durante ser entre parte cuatro ciudad fueron hay sobre desde además
    años seis puede actualmente siete nombre todo embargo ocho cinco año esto cuando gran nueve
    sido primera hasta mismo todos ese estos forma universidad primer cada han otros donde
    tiempo entonces están vida ella así estas mayor varios san bien luego vez algunos tuvo tras
    lugar pueden nacional tarde familia cero estaba equipo hijo tanto tienen color varias nueva
    nació historia estado grupo día padre había mundo muchos guerra solo cuenta principal
    carrera centro otras allí poco club obra antes hace sede bajo general todas siempre estudió
    algunas canción segunda sur ellos final posteriormente otro mejor sólo río siguiente españa
    partido película álbum música ambos nunca eso serie eran estudios veces país casa mucho
    norte aunque tenía muchas grandes nada diferentes trabajo otra estados zona ahora nuevo
    escuela hijos hacia obras importante agua esa hoy banda iglesia hizo unidos momento hacer
    capital junto toda finalmente comenzó madre nos sistema dentro mayoría provincia central
    segundo encuentran gobierno siendo menos contra pueblo miembro último estuvo temporada
    recibió presidente vamos región qué hecho tipo muerte mientras fútbol juan trata casi algo
    isla principalmente existen misma estilo especie internacional canciones juego ver ello aquí
    edificio municipio planta noche medio quien primeros madrid debe argentina realizó
    principales director título posee tener según número conocido origen actualidad les maría
    debido largo condado mar actual flores producción porque europa hombre caso derecho programa
    tierra natural vale presenta trabajó hija política personas tan real santa manera estación
    división hermano días teatro igual libro cabeza museo juega base disco televisión población
    países aún francia arte interior unos grande llegó blanco cuerpo niña pasó lleva joven
    especies última ojos chile hojas actividad cerca público lado estar ambas importantes
    proyecto habita muestra militar único distrito sigue mundial oficial parece pues versión
    mujer cargo selección costa obtuvo diversas suele español padres uso considerado edad barco
    papel diversos aparece profesor república popular localidad fuera existe ejemplo musical
    participó rey ocasiones numerosos quiero cine tengo favor estudio nombrado vive grupos honor
    amor hermanos china ganó meses ninguna negro nivel libros parque desarrollo original área
    jugador pequeño convirtió generalmente pequeños poder buena dicho estoy alto pronto equipos
    punto orden miembros áfrica murió movimiento conocida gente partes restos española gracias
    bosques pertenece servicio todavía proceso puedo incluso york resto tema mujeres relación
    cualquier campo quedó francisco partir alta juegos zonas asimismo menor estaban pequeña
    partidos dice bueno cosas matrimonio bastante puerto primero jugó clima única plantas sabe
    premio tal local sería educación liga radio islas línea buen brasil parís fuerte buenos
    haber sea superior frente numerosas conoce construcción carlos hábitat autor dicha compañía
    oeste actor camino utiliza revista alemania posición sencillo diez llamado tercera ante
    información california niño hermana incluye tenemos películas resultado barrio colegio
    instituto cambio mal sitio temas puesto colombia castillo civil actividades paso mediante
    común claro media torneo profesional será verdad pasado nadie batalla mano perú propio
    últimos suelo escribió verde dio volvió hombres personaje italia contiene social reino
    cantante amigo especialmente amigos calle territorio oro ningún niños primeras ellas
    departamento señor menudo trabajos formación australia juntos cultura cabo antiguo antigua
    actriz voz ayuda tuvieron decir barcelona valle dios tipos considera tercer luis servicios
    japón semana queda diseño economía puerta cual pequeñas unión hubo similar quiere
    agricultura victoria obstante azul cementerio siguientes plaza estructura modo problemas
    empresa santiago empezó novela londres edición luz sol casado dirección john modelo posible
    político baja sociedad pesar dejó pasa chole comienza fin críticas período verano acuerdo
    cruz ciencias principio tamaño manos situado llamada consejo aquel estamos premios rojo
    academia espacio mis conjunto piedra campeón elementos aguas antonio defensa decidió
    literatura comercial datos comunidad especial periodo persona casos pocos municipal llama
    propia lugares escrito inició logró asia continuó situación inglaterra campeonato ahí mes
    anterior venezuela unas aires nosotros visto personajes destaca occidental cubierta acción
    horas torre pedro libre causa esposa madera formó católica trabaja ciudades terminó larga
    situada fecha amarillo permite encontrar clase casó nave animales roma investigación habían
    recibe pareja falta alrededor lista fuente organización categoría julia suelen representa
    función total aire hacen van semillas policía lengua colores artes pintura jóvenes india
    sola llegar elegido industria demasiado dirigido carácter plata templo palabra dar has
    entrada propiedad tampoco esos realiza invierno toma fuerza dedicó podemos exterior creció
    fondo puente gusta enterrado aeropuerto puntos arquitectura realizar cabecera eres pudo
    versiones soy vino trabajar hora episodio filosofía cola figura considerada artistas publicó
    lago cómo incluyen etapa ubicado asociación jefe natal significa tropicales regresó miguel
    completamente acceso estadio villa blanca usa distintos video cultural capítulo continuación
    objetivo formas importancia red crítica artista deja imagen voy distintas palacio salir gira
    ministro histórico llevó tierras problema francesa difícil ganado catedral hospital creo
    relaciones fundación pie conserva letras tenían diario doce maestro programas referencia
    fuerzas cuarto produce abogado poesía deportivo influencia medios mejores vuelve publicado
    siento alas rápidamente unido nuevos adelante oriental cara ángeles tradición mayores
    personal humanos paz alguien pública clases tiempos tenido viaje david nacionales sector
    jardín áreas mil comunicación árboles nuevas control corazón viejo algún pan rock jugar
    vivió fuentes campaña normalmente aves hicieron montaña alguna presencia uruguay rusia
    locales edificios escuelas valencia don comisión cámara alemán actuación valor copa oscuro
    rica siguió llega solamente imperio podría musicales consta león jugadores arriba revolución
    playa vista doctor palabras probablemente aun idea secundaria reina fiesta variedad infancia
    escrita perro perdió naturales material salud doble lucha festival comercio escritor pocas
    productos caballo habla grado jugaba viene fase resultados marca fachada ubica dirigió esas
    dijo julio consiguió noroeste armas cantidad insectos habitantes dan apareció utilizado
    igualmente aparecen hemos ricardo cambios mayo podía inferiores corto ecuador juventud
    ubicada consiste decide pasar nuestra biblioteca relativamente turismo características ley
    mercado seguridad razón fruto haciendo entrenador tienes frontera casas deben militares
    empresas anteriormente teoría mitad críticos cosa forman administración artículos garcía
    alcalde cuanto canadá evento originalmente ofrece santo colección palomares condiciones ríos
    independiente
""".split()
