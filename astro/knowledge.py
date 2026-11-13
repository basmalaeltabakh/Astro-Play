# -*- coding: utf-8 -*-
"""Seed science knowledge base (English + Arabic, three reading levels).

IMPORTANT: these are short educational summaries written in our own words about topics covered by NASA
educational resources. They let the assistant work offline. For the full NASA-sourced knowledge base run
``python scripts/ingest_nasa.py`` (needs network). Always verify facts against the source pages.

Each topic has, per language: ``young`` (ages 6-9, very simple), ``mid`` (10-13) and ``deep`` (an extra
technical sentence; the teen level (14+) = mid + deep).  ``SEED_DOCS`` is the flattened list the assistant
indexes: {id, topics, level, lang, source, text}.
"""

# id, tags, source, {lang: (young, mid, deep)}
_TOPICS = [
    ("moon-atmosphere", ["moon", "atmosphere", "temperature"], "https://moon.nasa.gov/", {
        "en": ("The Moon has no air to breathe and no wind. In the Sun it gets super hot, and at night it gets freezing cold. Machines on the Moon need special blankets and heaters.",
               "The Moon has almost no atmosphere. Without air there is no wind, weather or sound, and heat is not carried away by moving air. That is why surface temperatures swing from above 100 degrees Celsius in sunlight to well below minus 100 at night.",
               "With nothing to trap or carry heat, the surface loses it only by radiating it into space, so the swing is about 250 degrees Celsius."),
        "ar": ("القمر ليس فيه هواء نتنفسه ولا رياح. في الشمس يصير حارًّا جدًّا، وفي الليل يصير شديد البرودة. لذلك تحتاج الآلات على القمر إلى أغطية خاصة ومدافئ.",
               "القمر شبه خالٍ من الغلاف الجوي. وبلا هواء لا توجد رياح ولا طقس ولا صوت، ولا يوجد هواء متحرك يحمل الحرارة بعيدًا. ولهذا تتأرجح حرارة سطحه من أكثر من 100 درجة مئوية في الشمس إلى أقل بكثير من 100 تحت الصفر ليلًا.",
               "ولأنه لا شيء يحبس الحرارة أو ينقلها، يفقدها السطح بالإشعاع إلى الفضاء فقط، فيبلغ التأرجح نحو 250 درجة مئوية.")}),
    ("moon-regolith", ["moon", "regolith", "dust", "rocks"], "https://moon.nasa.gov/", {
        "en": ("Moon dust is made of tiny sharp pieces of rock. Space rocks crashed into the Moon for a very long time and broke the ground into dust. It sticks to suits like glitter!",
               "Lunar regolith is a layer of loose broken rock and dust created by billions of years of meteoroid impacts. Because the Moon has no weather to erode it, the grains stay sharp and jagged and can cling to suits and equipment.",
               "Impacts can melt the soil into tiny glassy fragments, and static charge makes the dust cling to surfaces."),
        "ar": ("غبار القمر مصنوع من قطع صغيرة حادّة من الصخر. ظلّت صخور الفضاء تضرب القمر زمنًا طويلًا وتحوّل أرضه إلى غبار. وهو يلتصق بالبدلات كالبريق!",
               "الريغوليث القمري طبقة من الصخور المكسّرة والغبار السائب صنعتها مليارات السنين من اصطدامات النيازك. ولأن القمر بلا طقس يُنعّم الحبيبات تبقى حادّة وخشنة وتلتصق بالبدلات والمعدات.",
               "قد تُذيب الاصطدامات التربة إلى شظايا زجاجية صغيرة، كما تجعل الشحنة الكهربائية الساكنة الغبار يلتصق بالأسطح.")}),
    ("moon-solar-power", ["moon", "power", "solar", "battery"], "https://www.nasa.gov/", {
        "en": ("Solar panels turn sunlight into electricity. If dust covers them, they get less light. The Moon night is very long, so machines need batteries and warm blankets.",
               "Solar panels turn sunlight into electricity. Dust on the panels blocks sunlight and lowers power, and the long lunar night lasts about two Earth weeks, so batteries and insulation matter.",
               "Designers pair panels with dust mitigation and energy storage, because a single lunar night means about 14 days without sunlight."),
        "ar": ("الألواح الشمسية تحوّل ضوء الشمس إلى كهرباء. وإذا غطّاها الغبار وصلها ضوء أقل. وليل القمر طويل جدًّا، فتحتاج الآلات إلى بطاريات وأغطية دافئة.",
               "تحوّل الألواح الشمسية ضوء الشمس إلى كهرباء. والغبار على الألواح يحجب الضوء ويقلّل الطاقة، وليل القمر الطويل يمتدّ نحو أسبوعين أرضيين، لذلك يهمّ وجود البطاريات والعزل.",
               "يقرن المصمّمون الألواح بوسائل لمقاومة الغبار وتخزين الطاقة، لأن الليلة القمرية الواحدة تعني نحو 14 يومًا بلا ضوء شمس.")}),
    ("mars-water", ["mars", "water", "river", "delta"], "https://science.nasa.gov/mars/", {
        "en": ("Long, long ago Mars had rivers and lakes! Round pebbles and layered ground show where water once flowed. Today it is too cold and the air is too thin, so water can't stay liquid.",
               "Mars once had flowing water. Rounded pebbles, layered sediment and delta shapes in places like Jezero crater show where a river entered a lake. Today the air is too thin and cold for liquid water to remain stable on the surface.",
               "Orbiters and rovers have mapped delta deposits in Jezero, which hold sediments that may preserve signs of ancient environments."),
        "ar": ("قبل زمن بعيد جدًّا كان على المريخ أنهار وبحيرات! الحصى المستدير والأرض ذات الطبقات يدلّان على أن الماء كان يجري هنا. أما اليوم فالجو بارد جدًّا والهواء رقيق، فلا يبقى الماء سائلًا.",
               "كان على المريخ ماء جارٍ في الماضي. فالحصى المستدير والرواسب المتراصّة وأشكال الدلتا في أماكن مثل فوهة جيزيرو تُظهر أين دخل نهر إلى بحيرة. أما اليوم فالهواء رقيق وبارد جدًّا فلا يستقرّ الماء السائل على السطح.",
               "رسمت المدارات والمركبات الجوّالة خرائط لرواسب الدلتا في جيزيرو، وفيها رواسب قد تحفظ آثار بيئات قديمة.")}),
    ("mars-clay", ["mars", "water", "rocks", "clay", "life"], "https://science.nasa.gov/mars/", {
        "en": ("Clay is made when rock sits in water for a very long time. When scientists find clay on Mars, it tells them Mars used to be wet. Wet places are good for looking for tiny life.",
               "Clay minerals usually form when rock is in contact with liquid water for a long time. Finding clays on Mars tells scientists the planet was once wetter, and such places are good targets in the search for signs of ancient life.",
               "Clays can also trap and preserve organic molecules, which is why they are priority targets for sample collection."),
        "ar": ("الطين يتكوّن حين تبقى الصخرة في الماء زمنًا طويلًا جدًّا. وحين يجد العلماء طينًا على المريخ يعرفون أنه كان رطبًا. والأماكن الرطبة مناسبة للبحث عن حياة صغيرة جدًّا.",
               "تتكوّن المعادن الطينية عادةً حين تبقى الصخرة ملامسة لماء سائل زمنًا طويلًا. ووجود الطين على المريخ يخبر العلماء أنه كان أكثر رطوبة، وهذه الأماكن أهداف جيدة للبحث عن علامات حياة قديمة.",
               "يمكن للطين أيضًا أن يحبس الجزيئات العضوية ويحفظها، ولهذا هو هدف أساسي لجمع العيّنات.")}),
    ("mars-dust-rover", ["mars", "rover", "power", "dust", "solar"], "https://science.nasa.gov/mars/", {
        "en": ("Dust covers the rover's sun panels, so they make less power. Sometimes the wind blows the dust away. A rover can use a brush or a little shake, but not water.",
               "Dust settles on solar-powered rovers and reduces the power they make. On Mars, wind gusts have sometimes cleaned rover panels. Rovers can also use brushes or vibration, but not water, which would freeze or evaporate.",
               "Some rovers avoid the problem entirely by using a nuclear power source instead of solar panels."),
        "ar": ("يغطّي الغبار الألواح الشمسية للمركبة فتصنع طاقة أقل. وأحيانًا تهبّ الرياح وتُبعد الغبار. وقد تستخدم المركبة فرشاة أو هزّة صغيرة، لكن ليس الماء.",
               "يستقرّ الغبار على المركبات التي تعمل بالطاقة الشمسية ويقلّل ما تصنعه من طاقة. وعلى المريخ نظّفت هبّات الريح ألواح بعض المركبات أحيانًا. ويمكن للمركبات استخدام الفرش أو الاهتزاز، لكن ليس الماء الذي سيتجمّد أو يتبخّر.",
               "تتجنّب بعض المركبات المشكلة كليًّا باستخدام مصدر طاقة نووي بدل الألواح الشمسية.")}),
    ("mars-gravity", ["mars", "gravity", "atmosphere"], "https://science.nasa.gov/mars/", {
        "en": ("On Mars you would feel lighter than on Earth, so you could jump higher! The air on Mars is very thin and you could not breathe it.",
               "Mars has about 38 percent of Earth's surface gravity and an atmosphere about one percent as thick, made mostly of carbon dioxide.",
               "That thin carbon dioxide atmosphere holds little heat, which is one reason Mars is so cold."),
        "ar": ("على المريخ ستشعر بأنك أخفّ مما أنت على الأرض، فتقفز أعلى! والهواء على المريخ رقيق جدًّا ولا تستطيع تنفّسه.",
               "جاذبية سطح المريخ نحو 38 بالمئة من جاذبية الأرض، وغلافه الجوي أرقّ بنحو مئة مرّة ويتكوّن في معظمه من ثاني أكسيد الكربون.",
               "هذا الغلاف الرقيق من ثاني أكسيد الكربون يحتفظ بقليل من الحرارة، وهذا أحد أسباب برودة المريخ.")}),
    ("iss-freefall", ["orbit", "gravity", "microgravity", "float"], "https://www.nasa.gov/mission/station/", {
        "en": ("Astronauts float because they are falling around the Earth all the time, together with their spaceship. Gravity is still pulling on them!",
               "Astronauts on the International Space Station float because the station and everyone in it are in continuous free fall around Earth. Gravity at that height is still about 90 percent as strong as on Earth's surface.",
               "The station moves sideways at about 28,000 kilometers per hour, so as it falls it keeps missing the ground, which is what an orbit is."),
        "ar": ("يطفو رواد الفضاء لأنهم يسقطون حول الأرض طوال الوقت مع مركبتهم. والجاذبية ما زالت تشدّهم!",
               "يطفو رواد محطة الفضاء الدولية لأن المحطة وكل من فيها في سقوط حر مستمر حول الأرض. والجاذبية على ذلك الارتفاع ما زالت نحو 90 بالمئة من قوّتها على سطح الأرض.",
               "تتحرّك المحطة جانبيًّا بنحو 28 ألف كيلومتر في الساعة، فتظلّ وهي تسقط تخطئ الأرض، وهذا هو معنى المدار.")}),
    ("iss-co2", ["orbit", "life support", "air", "scrubber", "carbon dioxide"], "https://www.nasa.gov/mission/station/", {
        "en": ("When we breathe out, we make a gas called carbon dioxide. A special air cleaner catches it so the air stays fresh. When the cleaner is full, you swap in a new one.",
               "Spacecraft life support removes the carbon dioxide that crews exhale using scrubbers, and adds oxygen. In microgravity there is no convection, so fans are needed to keep air moving and stop pockets of carbon dioxide forming around a person.",
               "Without convection, warm exhaled air does not rise away from the face, so a still bubble of carbon dioxide can build up while sleeping."),
        "ar": ("حين نزفر نصنع غازًا اسمه ثاني أكسيد الكربون. وجهاز تنظيف خاص يلتقطه ليبقى الهواء نقيًّا. وحين يمتلئ المنظّف نضع واحدًا جديدًا.",
               "تُزيل أنظمة دعم الحياة في المركبات ثاني أكسيد الكربون الذي يزفره الطاقم باستخدام منقّيات، وتضيف الأكسجين. وفي الجاذبية الصغرى لا يوجد حمل حراري، لذا تلزم المراوح لتحريك الهواء ومنع تكوّن جيوب من ثاني أكسيد الكربون حول الشخص.",
               "وبلا حمل حراري لا يصعد الهواء الدافئ المزفور بعيدًا عن الوجه، فقد تتكوّن فقاعة ساكنة من ثاني أكسيد الكربون أثناء النوم.")}),
    ("iss-plants", ["orbit", "plants", "microgravity", "food"], "https://www.nasa.gov/mission/station/", {
        "en": ("Plants in space can't feel which way is down, so they follow the light and the water. Growing plants in space could give astronauts fresh food on long trips.",
               "Plants grown on the space station respond to light and moisture instead of gravity. Growing food in space could help feed crews on long missions.",
               "Without gravity cues, roots and shoots rely on light direction (phototropism) and water gradients, and growth systems must be designed around that."),
        "ar": ("النباتات في الفضاء لا تعرف أين الأسفل، فتتبع الضوء والماء. وزراعة النباتات في الفضاء قد تمنح الرواد طعامًا طازجًا في الرحلات الطويلة.",
               "تستجيب النباتات المزروعة في محطة الفضاء للضوء والرطوبة بدل الجاذبية. وزراعة الغذاء في الفضاء قد تساعد في إطعام الطواقم في المهمات الطويلة.",
               "وبلا إشارات الجاذبية تعتمد الجذور والسيقان على اتجاه الضوء (الانتحاء الضوئي) وتدرّج الماء، ويجب تصميم أنظمة الزراعة وفق ذلك.")}),
    ("europa-ocean", ["europa", "ocean", "ice", "life"], "https://europa.nasa.gov/", {
        "en": ("Europa is a moon of Jupiter covered in ice. Under the ice there is a giant salty ocean, with more water than all of Earth's oceans! Scientists wonder if tiny life could live there.",
               "Jupiter's moon Europa has an icy shell above a salty ocean that holds more water than all of Earth's oceans. Salts in the ice may come from that ocean.",
               "Hubble and Galileo observations suggest the ocean may exchange material with the surface, which would let a spacecraft sample it from above."),
        "ar": ("أوروبا قمر للمشتري مغطّى بالجليد. وتحت الجليد محيط مالح عملاق فيه ماء أكثر من كل محيطات الأرض! ويتساءل العلماء إن كانت حياة صغيرة تعيش هناك.",
               "لقمر المشتري أوروبا قشرة جليدية فوق محيط مالح يحوي ماءً أكثر من كل محيطات الأرض. وقد تأتي الأملاح في الجليد من ذلك المحيط.",
               "تشير ملاحظات هابل وغاليليو إلى أن المحيط قد يتبادل المواد مع السطح، ما يتيح لمركبة فضائية أخذ عيّنات منه من الأعلى.")}),
    ("europa-tidal", ["europa", "tidal heating", "jupiter", "gravity"], "https://europa.nasa.gov/", {
        "en": ("Jupiter's pull squeezes and stretches Europa, like squeezing a rubber ball again and again. That makes the inside a little warm, so the ocean stays liquid.",
               "Jupiter's gravity squeezes and stretches Europa as it orbits. This tidal flexing makes heat inside the moon and helps keep its ocean liquid.",
               "The flexing is stronger because Europa's orbit is slightly elliptical and tied in resonance with its neighboring moons."),
        "ar": ("جاذبية المشتري تضغط أوروبا وتشدّها، كمن يضغط كرة مطاطية مرّة بعد مرّة. فيصير داخله دافئًا قليلًا، ويبقى المحيط سائلًا.",
               "تضغط جاذبية المشتري أوروبا وتشدّها أثناء دورانه. ويولّد هذا الانثناء المدّي حرارة داخل القمر ويساعد على إبقاء محيطه سائلًا.",
               "ويزداد الانثناء لأن مدار أوروبا بيضاوي قليلًا ومرتبط برنين مع الأقمار المجاورة له.")}),
    ("europa-cold", ["europa", "temperature", "drill", "ice"], "https://europa.nasa.gov/", {
        "en": ("It is super, super cold on Europa. The ice there is as hard as a rock! A drill has to be warmed up first.",
               "Europa's surface is extremely cold, around minus 160 degrees Celsius, so ice there is as hard as rock. Tools must be heated and used carefully.",
               "At these temperatures ice becomes brittle and abrasive, and sunlight at Jupiter's distance is only about 4 percent as strong as at Earth."),
        "ar": ("البرد على أوروبا شديد جدًّا جدًّا. والجليد هناك صلب كالصخر! ويجب تسخين المثقاب أولًا.",
               "سطح أوروبا شديد البرودة، نحو 160 درجة مئوية تحت الصفر، فيصير الجليد هناك صلبًا كالصخر. ويجب تسخين الأدوات واستخدامها بحذر.",
               "عند هذه الحرارة يصير الجليد هشًّا وكاشطًا، وضوء الشمس عند بُعد المشتري لا يتجاوز نحو 4 بالمئة من قوّته على الأرض.")}),
    ("scientific-method", ["general", "method", "evidence"], "https://www.nasa.gov/stem/", {
        "en": ("Scientists are like detectives. They look closely, collect clues, guess what happened, and then test their guess.",
               "Scientists gather evidence, form an explanation, then test it. Good evidence comes from careful measurements that others can repeat.",
               "A strong explanation makes predictions that could be proven wrong; surviving repeated tests is what makes it trustworthy."),
        "ar": ("العلماء مثل المحققين. يراقبون بدقة، ويجمعون الأدلة، ويخمّنون ما حدث، ثم يختبرون تخمينهم.",
               "يجمع العلماء الأدلة ويكوّنون تفسيرًا ثم يختبرونه. والدليل الجيد يأتي من قياسات دقيقة يمكن للآخرين تكرارها.",
               "التفسير القوي يقدّم تنبّؤات يمكن إثبات خطئها؛ وبقاؤه صامدًا أمام الاختبارات المتكرّرة هو ما يجعله موثوقًا.")}),
]


def _build():
    docs = []
    for tid, tags, src, langs in _TOPICS:
        for lang, (young, mid, deep) in langs.items():
            for level, text in (("young", young), ("mid", mid), ("teen", mid + " " + deep)):
                docs.append({"id": f"{tid}-{lang}-{level}", "base": tid, "topics": list(tags), "level": level,
                             "lang": lang, "source": src, "text": text})
    return docs


SEED_DOCS = _build()
