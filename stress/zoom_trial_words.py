"""Words tried as Zoom's Spanish "others" (written down instead of a command they sound like).

near: words at least 72% like a one-word command (difflib), said at least 5 times in MSWC's Spanish.
top300, top1000, top3000: MSWC's most said Spanish words (Common Voice), three letters or more.
short: the one- and two-letter words MSWC leaves out.
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

TOP300 = """
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
    países aún francia arte interior unos grande llegó blanco cuerpo niña pasó
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

TOP3000 = """
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
    independiente capitán completo estudiantes mantuvo vía tradicional sentido sociales bosque
    volver tomó sistemas abajo izquierda estrella usted mira permaneció sierra marrón enfermedad
    trasladó políticas poeta escudo bolivia mucha reyes superficie corta guitarra presentan
    encontrado canal termina distribución web desarrolló piano calidad oye práctica derecha dado
    temporadas energía formado antiguos ayuntamiento fundador miedo efecto gobernador
    localidades proyectos corte buenas económica diferencia ganador boca veinte finales complejo
    quieres únicamente aspecto iba derechos fernando destino vivo treinta series apenas
    nuevamente vivir sirve originaria gris originario lanzamiento autores cielo inicialmente
    crecimiento abierto dónde graduó delantero extremo industrial sala martín mantiene sonido
    falleció sale simple college diferente totalmente ninguno plan libertad inferior demás
    realidad unidad luna hechos usado medicina fuego basada participación texto córdoba dinero
    revistas campos viento virgen jorge pico conocidos ruta regiones combate mañana entrar
    contrario nacido creación nombres aquellos ganadería anteriores particular terreno portugal
    empieza ataque presente españoles primavera asistió calles memoria realizado compuesta
    famoso amplia seguro posteriores rango frutos dulce cuba producido tropical huevos muerto
    concepto blancas naturaleza capilla públicas pesca viven hablar carretera internacionales
    dedicada frecuencia ministerio recibido dirigida líder salvador líneas tales semanas bajas
    vuelta reside cargos atrás comarca populares conciertos sino guinea piezas medalla escena
    octubre efectos italiano excepto ramas periódico ambiente montañas berlín deportes
    tratamiento estadounidense regional composición peces arquitecto comerciales cree eventos
    rosa james ciencia activo capacidad puedes feliz mexicano prisión tomar posterior mexicana
    hierro corona septiembre dispone velocidad medida apoyo acerca construido distancia banco
    prensa incluyendo quién niveles resistencia transporte aquella húmedos sección contenido
    jesús encontraba vas poseen lejos cuenca obispo llegado elecciones accidente carne primaria
    clásico necesario decisión seguir george nuestro funciones entró dedicado desempeñó venga
    vídeo encima patas publicación depende arena minutos evitar pintor respecto imágenes
    monumento perdido regreso titular distribuye cadena menores títulos cursó domingo acaba
    michael cierto tropas diego rico principios escribir adultos sevilla siglo figuras física
    ferrocarril éste diputado encontró muere formato comida experiencia licenciado estudiar
    modelos negra paul school atención ulises símbolo ven retiró novelas cuarenta tocar labor
    vio siguen mando colonia secretario paraguay misión prueba oficiales compositor después come
    publicaciones similares debajo árbol contacto pruebas inicio respuesta quedan debut
    inmediatamente animal comer historias dejar amistad juguete destacan city cuarta diócesis
    creó permanente cráter fiestas chicos agosto suerte cambiar llevan categorías planeta
    avenida duda alimenta hogar escenas ediciones caracteriza múltiples humano poemas suiza par
    objeto ainhoa recursos soldados compuesto normal periodista provincial convento vuelo curso
    operaciones mezcla rosario basa trabajando roja vegetación marido proviene coro parroquia
    vías bandas voces argentino sueño borde ejerció llevar lima prácticamente sitúa ramón
    cuidado editorial liberal también utilizan especiales monasterio quince productor residencia
    futuro punta federal necesito disponible corriente ascendencia ronda letra materiales
    estrellas reunión clubes producto participado realizan resultó caballos abril unidades
    orquesta corea reconocido mismos institución ganar quería panamá torres avión muestran
    congreso hacerlo alcanzó gonzález lenguas universidades junio haya números arco alberga
    capítulos comunes fundó escritas rodríguez canto protagonizada contrato motor vilma bellas
    junta tren pelea abarca piel directamente habitual independencia sangre usar logra familias
    patio obtener produjo núcleo ampliamente caja grabado altura metros desarrolla formar
    ligeramente presentó señora fuertes dientes crear morir chica vicente abandonó construyó
    nacimiento familiar destacó pies salida desconoce príncipe compone posiblemente económico
    pecho frío trabajado característica funciona florece colaboró halla ana diagrama agrícola
    competición cuerpos puertas comenzaron peligro saber casada monte justicia pasos valeria
    acto sufrió silencio largas fábrica privada sello marina hermanas enrique continúa pacífico
    mediterráneo asamblea chico suroeste denomina new hijas recuerda abierta urbano conoció
    políticos pablo brazos william exposiciones músico autoridad carreras rocas ruso conflicto
    inicial romano completa periodismo acabó encuentro delante lópez objetos grabación artística
    centros breve pinturas notable históricos espera camarote reserva sirvió generación portada
    homenaje once permanece crece alberto discos europeo frecuentemente oportunidad quinto pieza
    escenario diferencias saint lateral pista fernández lanzado realmente busca antiguas
    internet operación noviembre poca permitió página lee detrás alemana cita culturales
    exposición alma facultad conservan idioma ángel presentes llegaron baile celebra coronel
    naves austria coche ascenso fácilmente actores europea profesora cursos utilizar justo puso
    teniente consecuencia estaciones florida denominación martínez mantener fácil clasificación
    concurso profesión elemento construida razones duró rural arma ocasión rápido imposible
    poner otoño creado actuó moderna tabla ruinas viajó análisis producen máximo llevado
    recientemente requiere pone laterales verdadero ingeniero federación económicas bandera
    etapas existencia indica superiores motivo aparición realizaron piloto records deporte
    describe altas dieron textos caza cocina directo concierto ocurre paisaje machos propios
    trayectoria enseñanza religiosa pop parlamento interpretó corresponde interpretación
    convertirse corre tribunal duque fama británico pueblos destacado blancos thomas ocupa
    positivas carga constante allá dirige contó metal sudáfrica estatal jamás episodios santos
    producir pato compañero cuales suecia contaba indio trece ocupó ejemplos poblaciones
    representación teología isabel cama responsable abuelo viena chicago clave oriente brillante
    resulta negocios ámbito cien podían hacía intenta deportiva literaria sabor toca incluido
    volar comúnmente desarrollado caer estableció mata originales extensión tallos tecnología
    marcha amiga nativa caminos fines unió polonia divisiones representado somos lenguaje
    clásica hablando ideas usan estuvieron elección provincias emperador sonora construir
    propias muertos convierte secos comprende finalizar cataluña noruega aprendió peter cría
    instalaciones salió plato búsqueda carta fotografía vietnam show marcó sexual moderno
    protección motivos murieron histórica inglesa capaz comienzo dolor quedaron baloncesto
    contigo mala localiza concepción ido tratado artístico tradicionales iglesias alemanes
    movimientos bahía esperanza pasajeros simplemente municipios reconocimiento negras temprana
    refiere presión idiomas americano barcos golpe corteza desempeña batería divide sureste jazz
    hembras inicia doctorado constituye eduardo cultivo belleza roca escritos navidad consideran
    disputó músicos castilla patrimonio álbumes suelos aplicación papeles tío participar hola
    religión grecia alimentan instituciones decoración parecen egipto columnas usada noreste
    hambre protagonista marzo científicos materia humana participaron frecuente profesionales
    participa propiedades tailandia park gol bajos rectangular colaboración actuaciones music
    congo plano infantil llegada griego zaragoza diseñado griega vecinos oficialmente turístico
    entra pensar órdenes terminar código popularidad influencias compañeros bronce secundarios
    comandante hembra rafael enemigo instrumentos irlanda agencia ventana guardia destacar clara
    leyes ventas habría mesa cabe sudeste gómez planes culto dicen carmen reacción calor secreto
    poblado redes recibir seno condición gestión diciembre pobre peso sombra marino lanzó goles
    franco felipe hotel miles significado conocer plataforma conmigo herido oficinas vacaciones
    llegan vaya noticias autoridades futbolista territorios familiares famosa tus debió esperaba
    turquía caballero acciones víctimas expresión árabe febrero reinado ropa cantar obtiene
    interpretado costas catorce ingresó cincuenta filipinas cristo usualmente guion dije
    montevideo varía conocimiento judicial registro conocen metro oposición aspectos mudó
    nuestros raíces periódicos parroquial guillermo jardines flora veo arbustos últimas mostró
    británica dura italiana rara posiciones sectores programación laguna editor largos tesis
    basado socialista ubicación paredes espacios activa buscar utilizó orígenes abre
    relacionados nación siglos rojas washington actos fenómeno robert ópera milita compuestas
    masa consigue disponibles mas península totalidad cuentos fray error latín cambió agrícolas
    cientos matar smith inmigrantes conde duración propósito pese daños noticia visita espacial
    comunidades piti barrios universitario visión perros crisis viajes honduras nace comuna
    constitución religioso trabajadores poderes escapar previamente indonesia caliente burbuja
    amplio retirada sean producciones estás necesita negros oficina trenes nieve abrió tercero
    cercana bogotá sacerdote femenino ventanas debía indígenas zelanda barroco defensor usuarios
    riesgo vivos romana enorme seco declaró particularmente terminal cayó apertura altos irán
    fondos embajada jugando privado utilizada dependiendo venta intento volumen abrir alianza
    cultivos aplicaciones castellano misiones digital alimentos formada leche ermita presentado
    evolución juguetes simples dividida conocidas estudia caída gloria fundamental cierta
    reconocida propuesta democrática brazo parejas flor lados cuello sabes fauna quinta
    excelente cuadro marco piso contienen límite fortaleza solución identidad juez seminario inc
    entrega fuertemente papa casco habitualmente guatemala entorno estilos pueda estancia
    convertido posibilidad ficción escritura detalles conferencias boston producida cortes
    nativo escultura piedras crio comportamiento regresar europeos encuentros leyenda arcos
    serán abandonar negó gamboa grados mandato posibles dominio regresa variedades juicio
    charles reforma tormenta ejecución high debate matemáticas millones pertenecía verdes salón
    serían juvenil nombró israel cáncer king recorrido reales apariencia enero conservación
    recuperar muros bretaña cura richard puestos enamorado escribe ritmo loco film noble
    terminado ingeniería vehículos ideal femenina macho individuales tono momentos hubiera
    máxima procesos archivo sucedió notas roberto cercano man distribuyen nota ceremonia compuso
    torno sencillos labios deriva violencia opera mamíferos frecuentes espíritu parecía
    compuestos cubierto carolina dedos cuentan sobrino colecciones judíos estudiante pez
    adolescente provocó decidieron asistente ataques perteneció vuelos escritores naranja
    talento artículo secciones órgano ciertas cerro veracruz esperar empezar urbana acompañado
    retirarse quienes expedición lope denominado warner química tumba pasan motores impacto
    descendencia promoción dedica martin aceptó mario temporal rodeado esposo cambiado romanos
    llevaba actuar pasión estructuras estándar ciclo fundadores negocio llamó templado franceses
    salas louis republicano semifinales pudieron heridos moscú lagos directa públicos duro
    aceite single lleno ciertos universo surgió físico murmuró electoral sombrero conseguir
    teatral escala homónima dibujo derrota dime competencia ejemplares bóveda kilómetros tiendas
    competiciones lograron recibieron une docente league regular extiende software ramiro humor
    botánico camerún chileno liceo hielo componentes brown tomado aparecido limita dinastía
    agente llaman guitarrista santuario cortos venir marcas ernesto civiles metropolitana playas
    cañón parecer imperial gustan raro techo lluvia dieta asociado autónoma palo rojizo
    regionales joseph contrajo alcanzar audiencia solitario siguieron primo extranjero compañías
    distritos columna castro subtropicales fracaso triste cae galería rumbo dinamarca canta
    religiosas investigaciones pantalla documental mismas organizaciones retratos margen gato
    disputa danza malasia fósiles minas comedia carece indios temperatura senador cuestión
    abundante próximo alimentación católico documentos salvo festivales paseo ayudar teorías
    representan pierde vivía ejecutivo antiguamente crea tallo objetivos nieto espectáculo
    británicos frutas encontramos judía caracas cerámica grabó interesante tour juveniles selva
    princesa kenia cabello rendimiento señal pilotos patrón fresco aparecer administrativo guía
    húmedas circular realizada causas adicionales dominicana guerras ésta típico vuelven
    publicada opción armada eje bros henry encontrarse verse sonata raíz integró tramo
    fabricación izquierdo pisos gas usando especializó tira declarado soldado cerrado cordillera
    leer haga intentó adaptación gana longitud demanda cárcel maíz guzmán llevaron valores
    continental cinta flota navarra retablo proporciona encargado cortas sobrevivió pide diga
    dando hábitats crema cuya noches gracia malo denominada cobre comunista hacienda vidas
    ciento traje científico utilizados recinto alumnos absoluto novia vehículo descubre paisajes
    suficiente llena acabar estela jugado golfo utilizando altar escolar university young
    cápsula habilidades debutó dibujos encontraron boda dividido candidato descubierto hermoso
    dimensiones alegría setenta trabajaba grabaciones queso talleres relieve pecado asesor
    reglas bienes seguido actuales dedicarse húmedo ave profundo equivalente medieval rusa
    garganta instrumento milán individuos alrededores perenne inicios firmó presentar williams
    fotografías aproximadamente vecino arroyo enviado volante dices publica alcance javier raza
    vocal conferencia podido parcialmente jones miel nicaragua gótico salieron guerrero terrenos
    escucha documento generales nigeria oxford especialidad escasa lisa recuerdo círculo
    ladrillo tienda mediados adolescencia torneos escocia mensaje trono científica love tendrá
    separado hungría estatua ocurrió certamen jack von privadas conexión opinión traducción
    sitios prisioneros tom pardo invitado andalucía matorrales serio perder combustible desierto
    síntomas aragón religiosos beso seda manchas vienen miami rápida mecanismo apellido naval
    tenga cristiana nicolás hollywood incidente controlar viviendas solar económicos continuar
    continúan pena límites modernos siente fruta sánchez considerable vegetales humilde levantó
    historiador reciente espinas heridas concejo suave jurado entidad poblada sonidos fechas
    finalizó destinado representante dormir monedas enfermedades aviones vuelto detenido vasco
    emplea tendencia rutas ciudadanos participantes americana mitología atraviesa listas
    prefiere basta abiertos selvas crítico empleo pregunta cabezas hacerse maestra aprender
    hecha pensaba procede asesinato restaurante nacionalidad corrientes dolores dichos chino
    palma escritora marcado taller órganos libres ruido factor cuento orilla tarea marta
    designado centra terrestres licenciatura dorado destrucción turistas interpreta ordenó
    referencias factores cuyo acero vientos pescado ojo fuese universal lentamente campañas
    abundantes centrales interpretada publicados salvar mancha pensamiento dra presentación
    habitación sra asesinado sexo herramientas anunció estrecho usuario milagro lectura doctora
    ingleses directora usos definición expansión american dificultad batallas cubiertas mary
    ábside trataba vocalista enterrada extranjeros dichas cumplir ácido incorporó descubrió
    debería plumaje valladolid intentar pidió iban transmisión notables desapareció lorenzo bar
    acepta tiro contexto misa regalos ignacio localizado marcos chilena altamente orillas habrá
    abuela rasgos poema piensa west capillas consumo desconocido disciplina homónimo interna
    doña canales ensayos taiwán retirado algas primarios enseñó marruecos tanzania violín lento
    georgia presidencia gravemente multitud formando darle páginas cúpula circuito aprendizaje
    derrotado permiten reemplazado vicepresidente dejado sebastián extinción lema alguno rama
    refugio comprar potencial pasaron ganadores dificultades salta dictadura invitados borneo
    scott solista temperaturas continuaron gestiona oscura diversidad saga reducido ayer habido
    agrupación luchó tocó floración quieren completó moda enemigos pájaros pelo feria temática
""".split()

SHORT = "de la el en y a se un es al lo no su le me mi ha si o e ya te tu yo ni".split()
