# -*- coding: utf-8 -*-
"""All player-facing mission text, in English and Arabic, with simpler wording for young players.

``tx(en, ar, en_young, ar_young)`` builds a text spec.  ``pick(spec, lang, age)`` resolves it:
ages 'mid' and 'teen' use the standard wording, 'young' (6-9) uses the simplified wording when given.
"""
from typing import Dict


def tx(en, ar, en_y=None, ar_y=None):
    return {"en": {"std": en, "young": en_y or en}, "ar": {"std": ar, "young": ar_y or ar}}


def pick(spec, lang="en", age="mid"):
    d = spec.get(lang) or spec["en"]
    return d["young"] if age == "young" else d["std"]


# (display name, text) per mission.  Option order MUST match the option order in missions.py
MISSION_TEXT: Dict[str, dict] = {
    "moon": {
        "name": tx("Lunar Outpost Blackout", "انقطاع الكهرباء في قاعدة القمر"),
        "briefing": tx(
            "Power has failed at the lunar outpost. Investigate the equipment, gather evidence about the lunar environment, and restore power.",
            "انقطعت الكهرباء عن قاعدة القمر. افحص المعدات، واجمع أدلة عن بيئة القمر، وأعد التيار الكهربائي.",
            "The lights went out at our Moon base! Look around, learn about the Moon, and turn the power back on.",
            "انطفأت الأنوار في قاعدتنا على القمر! تجوّل وتعلّم عن القمر، ثم أعد تشغيل الكهرباء."),
        "science": tx("Airless worlds, dust, and temperature extremes", "عوالم بلا هواء، والغبار، ودرجات الحرارة المتطرفة",
                      "No air, space dust, and very hot and very cold", "لا هواء، وغبار الفضاء، وحرارة شديدة وبرودة شديدة"),
        "deep": tx(
            "Deep dive: with no atmosphere, heat can only leave by radiation, so a lunar surface near the equator swings by roughly 250 degrees Celsius between day and night.",
            "للمتعمّقين: بلا غلاف جوي لا تفقد الأجسام حرارتها إلا بالإشعاع، لذلك يتأرجح سطح القمر قرب خط الاستواء بنحو 250 درجة مئوية بين النهار والليل."),
        "objects": {
            "solar_array": {
                "name": tx("Solar Array", "الألواح الشمسية"),
                "fact": tx("The Moon has almost no atmosphere, so there is no wind or rain to clean surfaces. Lunar dust is sharp and clings to panels and suits.",
                           "القمر شبه خالٍ من الغلاف الجوي، فلا رياح ولا أمطار لتنظيف الأسطح. وغبار القمر حادّ ويلتصق بالألواح والبدلات.",
                           "The Moon has no wind or rain to wash things clean. Moon dust is sharp and sticks to everything!",
                           "ليس على القمر رياح ولا مطر ليغسل الأشياء. وغبار القمر حادّ ويلتصق بكل شيء!")},
            "regolith": {
                "name": tx("Regolith Patch", "بقعة تربة القمر"),
                "fact": tx("This loose layer of broken rock is called regolith.", "هذه الطبقة السائبة من الصخور المكسّرة تُسمّى الثرى القمري (الريغوليث).",
                           "This crumbly Moon soil is called regolith.", "هذه التربة المتفتّتة على القمر اسمها الريغوليث."),
                "analysis": tx("Jagged, glassy grains. Meteoroid impacts made them, and with no weather to wear them smooth they stay sharp.",
                               "حبيبات حادّة وزجاجية. صنعتها اصطدامات النيازك، وبلا طقس يُنعّمها تبقى حادّة.",
                               "The grains are sharp like tiny glass. Space rocks smashed into the Moon and made them, and nothing smooths them down.",
                               "الحبيبات حادّة كالزجاج الصغير. صنعتها صخور الفضاء حين ضربت القمر، ولا شيء يُنعّمها.")},
            "power_relay": {
                "name": tx("Power Relay", "محطة توزيع الطاقة"),
                "fact": tx("Readings swing wildly between lunar day and lunar night.", "القراءات تتأرجح بشدة بين نهار القمر وليله.",
                           "Its numbers jump up and down between Moon day and Moon night.", "أرقامها تقفز صعودًا وهبوطًا بين نهار القمر وليله."),
                "fault": tx("The relay's temperature swings from over 100°C in sunlight to far below -100°C at night, and its circuits are failing.",
                            "تتأرجح حرارة المحطة من أكثر من 100°م في ضوء الشمس إلى ما دون -100°م ليلًا، ودوائرها تتعطّل.",
                            "In the Sun it gets super hot, and at night it gets freezing cold. The machine is getting sick from that!",
                            "في الشمس تصير ساخنة جدًا، وفي الليل باردة جدًا. والجهاز يتعب من ذلك!"),
                "options": [
                    (tx("Add thermal insulation and a heater", "أضف عازلًا حراريًا ومدفأة"),
                     tx("Insulation and heaters keep electronics inside a safe temperature range.",
                        "العزل والمدافئ يُبقيان الأجهزة الإلكترونية ضمن حرارة آمنة.",
                        "A warm blanket and a heater keep machines cozy, not too hot and not too cold.",
                        "بطانية دافئة ومدفأة تُبقيان الجهاز مرتاحًا، لا حارًّا ولا باردًا.")),
                    (tx("Install a cooling fan", "ركّب مروحة تبريد"),
                     tx("Fans push air around, but the Moon has almost no air to move.",
                        "المراوح تُحرّك الهواء، لكن القمر لا يكاد يملك هواءً ليتحرّك.",
                        "Fans move air, but the Moon has almost no air!", "المراوح تحرّك الهواء، لكن القمر لا هواء فيه تقريبًا!")),
                    (tx("Spray it with water", "رُشّه بالماء"),
                     tx("Water would boil away or freeze in the vacuum.", "الماء سيتبخّر بسرعة أو يتجمّد في الفراغ.",
                        "Water would turn to steam or ice right away in space.", "الماء سيتحوّل فورًا إلى بخار أو جليد في الفضاء.")),
                    (tx("Paint it black", "اطلِه باللون الأسود"),
                     tx("A dark surface absorbs more heat and worsens daytime overheating.",
                        "السطح الداكن يمتصّ حرارة أكثر ويزيد سخونة النهار.",
                        "Black things soak up more heat, so it would get even hotter!", "الأشياء السوداء تمتصّ حرارة أكثر، فتزداد سخونة!")),
                ]},
        },
    },
    "mars": {
        "name": tx("Mars: Search for Ancient Water", "المريخ: البحث عن الماء القديم"),
        "briefing": tx(
            "Our rover is losing power while exploring an ancient river delta. Find evidence of water and get the rover working again.",
            "المركبة الجوّالة تفقد طاقتها أثناء استكشاف دلتا نهر قديم. ابحث عن أدلة على الماء وأعد المركبة إلى العمل.",
            "Our little rover is getting tired on Mars! Find clues about water long ago, then help the rover get its power back.",
            "مركبتنا الصغيرة تتعب على المريخ! ابحث عن أدلة على وجود ماء قديم، ثم ساعدها لتستعيد طاقتها."),
        "science": tx("Water, rocks, and life-friendly places on Mars", "الماء والصخور والأماكن الصالحة للحياة على المريخ",
                      "Water and rocks on Mars", "الماء والصخور على المريخ"),
        "deep": tx(
            "Deep dive: clay minerals form through long-term water-rock reactions, which is why Jezero's delta clays are prime targets for sampling and possible biosignature searches.",
            "للمتعمّقين: تتكوّن معادن الطين عبر تفاعلات طويلة بين الماء والصخر، ولهذا تُعدّ طين دلتا فوهة جيزيرو هدفًا مهمًّا لجمع العيّنات والبحث عن علامات حياة محتملة."),
        "objects": {
            "riverbed": {
                "name": tx("Dry Riverbed", "مجرى نهر جافّ"),
                "fact": tx("Rounded pebbles and layered sediment are signs of flowing water. Jezero crater has a fan-shaped delta where a river once entered a lake.",
                           "الحصى المستدير والرواسب المتراصّة علامتان على جريان الماء. في فوهة جيزيرو دلتا على شكل مروحة دخل عندها نهر إلى بحيرة يومًا ما.",
                           "Round smooth pebbles are a clue: water once flowed here and rolled them around!",
                           "الحصى الأملس المستدير دليل: كان الماء يجري هنا ويُدحرج الحصى!")},
            "clay_rock": {
                "name": tx("Clay Rock", "صخرة طينية"),
                "fact": tx("A pale, layered rock stands out from the red dust.", "صخرة شاحبة متعدّدة الطبقات تبرز وسط الغبار الأحمر.",
                           "A pale rock with stripes sits in the red dust.", "صخرة شاحبة مخطّطة وسط الغبار الأحمر."),
                "analysis": tx("Clay minerals found. Clays usually form when rock sits in liquid water for a long time, so this rock is evidence of a wetter Mars.",
                               "وُجدت معادن طينية. يتكوّن الطين عادةً حين تبقى الصخرة في ماء سائل زمنًا طويلًا، فهذه الصخرة دليل على مريخ أكثر رطوبة.",
                               "It has clay in it! Clay forms when rock sits in water for a very long time. So Mars used to be wet!",
                               "فيها طين! والطين يتكوّن حين تبقى الصخرة في الماء زمنًا طويلًا. إذن كان المريخ رطبًا!")},
            "rover": {
                "name": tx("Science Rover", "المركبة العلمية الجوّالة"),
                "fact": tx("Rover power output looks low.", "طاقة المركبة تبدو منخفضة.", "The rover has very little power.", "طاقة المركبة قليلة جدًا."),
                "fault": tx("Power output has dropped by about 40% and the solar panels are caked in dust.",
                            "انخفضت الطاقة بنحو 40% وألواحها الشمسية مغطّاة بالغبار.",
                            "Its sun panels are covered in red dust, so they can't catch sunlight.",
                            "ألواحها الشمسية مغطّاة بالغبار الأحمر، فلا تستطيع التقاط ضوء الشمس."),
                "options": [
                    (tx("Shake the dust off with the vibration tool", "انفض الغبار بأداة الاهتزاز"),
                     tx("Vibration or a wind gust can clear dust without water.", "الاهتزاز أو هبّة ريح يزيلان الغبار دون ماء.",
                        "A gentle shake makes the dust fall off. No water needed!", "هزّة لطيفة تُسقط الغبار. لا حاجة للماء!")),
                    (tx("Rinse the panels with water", "اشطف الألواح بالماء"),
                     tx("Liquid water cannot last on Mars's surface: the air is thin and cold, so it freezes or evaporates.",
                        "لا يبقى الماء السائل على سطح المريخ: الهواء رقيق وبارد، فيتجمّد أو يتبخّر.",
                        "Water can't stay liquid on Mars. It freezes or disappears!", "الماء لا يبقى سائلًا على المريخ. يتجمّد أو يختفي!")),
                    (tx("Add bigger batteries", "أضف بطاريات أكبر"),
                     tx("Batteries store power; they don't make more. Dusty panels would still be starved.",
                        "البطاريات تخزّن الطاقة ولا تصنعها. والألواح المغبرّة تبقى جائعة للطاقة.",
                        "Batteries only keep power. They can't make new power.", "البطاريات تحفظ الطاقة فقط، ولا تصنع طاقة جديدة.")),
                    (tx("Turn up the heaters", "ارفع قوة المدافئ"),
                     tx("Heaters use even more power, making the shortage worse.", "المدافئ تستهلك طاقة أكثر فتزداد المشكلة سوءًا.",
                        "Heaters use even more power, so it gets worse.", "المدافئ تستهلك طاقة أكثر، فتزداد المشكلة.")),
                ]},
        },
    },
    "orbital": {
        "name": tx("Orbital Lab Emergency", "طوارئ في المختبر المداري"),
        "briefing": tx(
            "Air quality is dropping aboard the orbital lab. Study life in microgravity and fix the life-support system.",
            "جودة الهواء تتراجع على متن المختبر المداري. ادرس الحياة في الجاذبية الصغرى وأصلح نظام دعم الحياة.",
            "The air inside our space lab is getting stuffy! Learn how things float in space, then fix the air machine.",
            "الهواء داخل مختبرنا الفضائي صار خانقًا! تعلّم كيف تطفو الأشياء في الفضاء، ثم أصلح جهاز الهواء."),
        "science": tx("Microgravity, free fall, and life support", "الجاذبية الصغرى، والسقوط الحر، ودعم الحياة",
                      "Floating in space and the air we breathe", "الطفو في الفضاء والهواء الذي نتنفّسه"),
        "deep": tx(
            "Deep dive: in microgravity there is no convection, so exhaled CO2 can pool around your face. Stations use fans plus CO2 scrubbers to keep air mixed and clean.",
            "للمتعمّقين: في الجاذبية الصغرى لا يحدث تيّار حمل حراري، فقد يتجمّع ثاني أكسيد الكربون المزفور حول وجهك. لذلك تستخدم المحطات مراوح ومنقّيات لثاني أكسيد الكربون لخلط الهواء وتنقيته."),
        "objects": {
            "earth_window": {
                "name": tx("Earth Window", "نافذة الأرض"),
                "fact": tx("Astronauts float because they are in continuous free fall around Earth, not because gravity is missing. At the ISS's height gravity is still about 90% as strong as on the ground.",
                           "يطفو رواد الفضاء لأنهم في سقوط حر مستمر حول الأرض، لا لأن الجاذبية غائبة. وعلى ارتفاع المحطة الدولية تبقى الجاذبية نحو 90% من قوّتها على الأرض.",
                           "Astronauts float because they keep falling around the Earth, together with their spaceship. Gravity is still pulling!",
                           "يطفو رواد الفضاء لأنهم يسقطون حول الأرض طوال الوقت مع مركبتهم. والجاذبية ما زالت تشدّهم!")},
            "plant_rack": {
                "name": tx("Plant Rack", "رفّ النباتات"),
                "fact": tx("Plants in microgravity have no 'down'.", "النباتات في الجاذبية الصغرى ليس لديها «أسفل».",
                           "In space, plants can't tell which way is down.", "في الفضاء لا تعرف النباتات أين الأسفل."),
                "analysis": tx("Healthy leaf. In orbit plants use light direction and moisture to guide growth, and could help supply food on long trips.",
                               "ورقة سليمة. في المدار تعتمد النباتات على اتجاه الضوء والرطوبة لتوجيه نموّها، وقد تساعد في توفير الغذاء في الرحلات الطويلة.",
                               "A healthy leaf! Plants in space follow the light and the water to grow. They could be food on long trips.",
                               "ورقة سليمة! تتبع النباتات في الفضاء الضوء والماء لتنمو. وقد تكون طعامًا في الرحلات الطويلة.")},
            "scrubber": {
                "name": tx("CO2 Scrubber", "منقّي ثاني أكسيد الكربون"),
                "fact": tx("The cartridge indicator is red.", "مؤشّر الخرطوشة أحمر.", "The cartridge light is red.", "ضوء الخرطوشة أحمر."),
                "fault": tx("Carbon dioxide is building up in the module and the scrubber cartridge is saturated.",
                            "ثاني أكسيد الكربون يتراكم في الوحدة وخرطوشة المنقّي ممتلئة.",
                            "The air cleaner is full, so the stuffy air stays in the room.",
                            "منظّف الهواء ممتلئ، فيبقى الهواء الخانق في الغرفة."),
                "options": [
                    (tx("Replace the saturated cartridge", "استبدل الخرطوشة الممتلئة"),
                     tx("Scrubbers capture the CO2 astronauts exhale; once full they must be replaced.",
                        "تلتقط المنقّيات ثاني أكسيد الكربون الذي يزفره الرواد، وحين تمتلئ يجب استبدالها.",
                        "The cleaner catches the air we breathe out. When it's full, we put in a fresh one!",
                        "المنظّف يلتقط الهواء الذي نخرجه من صدورنا. وحين يمتلئ نضع واحدًا جديدًا!")),
                    (tx("Open the hatch to vent the air", "افتح الباب لتهوية الهواء"),
                     tx("Venting would lose breathable air. Outside is a vacuum.", "التهوية ستُضيّع الهواء الصالح للتنفّس. والخارج فراغ.",
                        "We would lose all our air! Outside is empty space.", "سنخسر كل الهواء! الخارج فضاء فارغ.")),
                    (tx("Add more oxygen", "أضف المزيد من الأكسجين"),
                     tx("More oxygen doesn't remove CO2; it would keep building up.", "المزيد من الأكسجين لا يُزيل ثاني أكسيد الكربون، فسيواصل التراكم.",
                        "Extra oxygen doesn't clean away the stuffy air.", "الأكسجين الإضافي لا يُزيل الهواء الخانق.")),
                    (tx("Switch the lights off", "أطفئ الأنوار"),
                     tx("Lights have nothing to do with removing CO2.", "الأنوار لا علاقة لها بإزالة ثاني أكسيد الكربون.",
                        "Lights don't clean the air.", "الأنوار لا تنظّف الهواء.")),
                ]},
        },
    },
    "europa": {
        "name": tx("Europa: Under the Ice", "أوروبا: تحت الجليد"),
        "briefing": tx(
            "Our drill team is stuck on Jupiter's icy moon. Investigate the ice, look for signs of a hidden ocean, and free the drill.",
            "فريق الحفر عالق على قمر المشتري الجليدي. افحص الجليد، وابحث عن علامات محيط مخفيّ، وحرّر المثقاب.",
            "Our drill is stuck on Jupiter's icy moon! Look for clues about a secret ocean, then get the drill moving.",
            "مثقابنا عالق على قمر المشتري الجليدي! ابحث عن أدلة على محيط سرّي، ثم حرّر المثقاب."),
        "science": tx("Ice moons, tidal heating, and subsurface oceans", "الأقمار الجليدية، والتسخين المدّي، والمحيطات تحت السطح",
                      "Ice moons and hidden oceans", "الأقمار الجليدية والمحيطات المخفيّة"),
        "deep": tx(
            "Deep dive: Europa's orbit is slightly elliptical, so Jupiter's tides keep flexing the moon. That friction heats the interior and may keep the ocean liquid for billions of years.",
            "للمتعمّقين: مدار أوروبا بيضاوي قليلًا، فتظل مدّات المشتري تثني القمر. ويسخّن هذا الاحتكاك الداخل وقد يُبقي المحيط سائلًا مليارات السنين."),
        "objects": {
            "ice_ridge": {
                "name": tx("Ice Ridge", "حافة جليدية"),
                "fact": tx("Europa is covered by an ice shell. Cracks and ridges suggest the ice flexes as Jupiter's gravity squeezes and stretches the moon, which creates heat inside.",
                           "يغطّي أوروبا قشرة من الجليد. وتوحي الشقوق والحواف بأن الجليد ينثني حين تضغط جاذبية المشتري القمر وتشدّه، فيتولّد حرّ في الداخل.",
                           "Europa wears a shell of ice. Jupiter squeezes and stretches the moon, which makes cracks and a little heat inside.",
                           "يرتدي أوروبا قشرة من الجليد. والمشتري يضغطه ويشدّه، فتظهر شقوق وتتولّد حرارة قليلة في الداخل.")},
            "salt_ice": {
                "name": tx("Salty Ice", "جليد مالح"),
                "fact": tx("Reddish-brown stains streak the ice here.", "بقع بنية محمرّة تخطّ الجليد هنا.",
                           "Brown-red stains streak the ice.", "بقع بنية حمراء على الجليد."),
                "analysis": tx("Salts mixed into the ice. They may have risen from a salty ocean believed to lie beneath the shell, which makes Europa a top place to search for habitable worlds.",
                               "أملاح ممتزجة بالجليد. ربما صعدت من محيط مالح يُظنّ أنه تحت القشرة، ما يجعل أوروبا من أفضل الأماكن للبحث عن عوالم صالحة للحياة.",
                               "Salt in the ice! It may come from a salty ocean hidden underneath. That's a great place to look for life!",
                               "ملح في الجليد! ربما جاء من محيط مالح مخفيّ تحته. وهذا مكان رائع للبحث عن الحياة!")},
            "drill": {
                "name": tx("Ice Drill", "مثقاب الجليد"),
                "fact": tx("The drill head is frozen solid.", "رأس المثقاب متجمّد تمامًا.", "The drill tip is frozen stuck.", "رأس المثقاب متجمّد وعالق."),
                "fault": tx("The drill tip is stuck. Surface temperatures are colder than -150°C, where ice is as hard as rock.",
                            "رأس المثقاب عالق. حرارة السطح أبرد من -150°م، حيث يصير الجليد صلبًا كالصخر.",
                            "It is so cold here that ice is hard like a rock, and the drill is stuck.",
                            "البرد هنا شديد حتى إن الجليد صلب كالصخر، والمثقاب عالق."),
                "options": [
                    (tx("Warm the drill tip, then drill slowly", "سخّن رأس المثقاب ثم احفر ببطء"),
                     tx("Heating the tip softens the contact ice and avoids snapping the bit.",
                        "تسخين الرأس يلين الجليد الملامس له ويمنع انكسار المثقاب.",
                        "A warm tip softens the ice, so the drill can go in gently.", "الرأس الدافئ يلين الجليد، فيدخل المثقاب بلطف.")),
                    (tx("Spin the drill faster", "أدِر المثقاب أسرع"),
                     tx("Brute force on rock-hard ice risks breaking the drill.", "القوة المفرطة على جليد صلب كالصخر قد تكسر المثقاب.",
                        "Too much force could break the drill!", "القوة الزائدة قد تكسر المثقاب!")),
                    (tx("Pour water on the tip", "اسكب الماء على الرأس"),
                     tx("Water would freeze instantly and make the jam worse.", "سيتجمّد الماء فورًا ويزيد العلوق سوءًا.",
                        "The water would freeze at once and make it worse.", "سيتجمّد الماء فورًا ويزيد الأمر سوءًا.")),
                    (tx("Wait for daytime to melt the ice", "انتظر النهار ليذيب الجليد"),
                     tx("Even at midday Europa stays far below freezing; sunlight is weak at Jupiter's distance.",
                        "حتى عند الظهيرة يبقى أوروبا أبرد بكثير من التجمّد، فضوء الشمس ضعيف عند بُعد المشتري.",
                        "Even in daytime it is still super cold here. The Sun is very far away.", "حتى في النهار يبقى البرد شديدًا هنا. فالشمس بعيدة جدًا.")),
                ]},
        },
    },
}

# Repair-option indices that are correct are defined in missions.py (always index 0 here).
ACHIEVEMENT_KEYS = ("first_mission", "flawless", "scientist", "problem_solver", "explorer", "level_5")
