from assets.const.pokemon_data import POKE_BALLS_LIST


# Optimal Economic Defaults
# S: Everything (Catch at all costs)
uncapt_S_default = [b for b in POKE_BALLS_LIST if b != "repeat_ball"]
S_default = POKE_BALLS_LIST

# A: High Value, but maybe save Master. Use Ultra/Specials.
# Economy: Avoid waste, but A tier is valuable.
A_balls = ["ultra_ball", "great_ball", "timer_ball", "quick_ball", 
           "level_ball", "lure_ball", "moon_ball", "friend_ball", "love_ball", "fast_ball", "heavy_ball", 
           "net_ball", "dive_ball", "nest_ball", "repeat_ball", "dusk_ball", "luxury_ball", "premier_ball"]
uncapt_A_default = [b for b in A_balls if b != "repeat_ball"]
A_default = A_balls

# B: Medium Value. Great Ball is workhorse. Ultra if needed.
# Economy: Prefer Great Ball (Cost 600) over Ultra (1000) unless necessary.
B_balls = ["great_ball", "timer_ball", "quick_ball", "net_ball", "dive_ball", "dusk_ball", "nest_ball", "repeat_ball"]
uncapt_B_default = [b for b in B_balls if b != "repeat_ball"] + ["ultra_ball"] # Boost for new entry
B_default = B_balls

# C: Low Value. Poke Ball only mostly.
# LogicDealer already restricts Great Ball usage for C tier based on cash.
C_balls = ["poke_ball", "great_ball", "premier_ball"]
uncapt_C_default = ["poke_ball", "great_ball", "premier_ball", "timer_ball", "quick_ball"] # Boost for new entry
C_default = C_balls

# M (Mission): Catch based on requirement, but usually any ball fails if not matched.
# Safest is to allow all except Master.
M_default = [b for b in POKE_BALLS_LIST if b != "master_ball"]
uncapt_M_default = [b for b in M_default if b != "repeat_ball"]


config_validator = {
    # A config object to validate config.json. We opted for a python dict so we do not have to load a json file here

    "language": {
        "default": "pt-br",
        "validator": {"type": "str", "accepted_values": ["pt-br", "es-la", "en-us"]}
    },
    "channel": {
        "default": "deemonrider",
        "validator": {"type": "str"}
    },
    "shop": {
        "poke_ball": {
            "buy_on_missing": {
                "default": True,
                "validator": {"type": "bool"}
            },
            "buy_one": {
                "default": 300,
                "validator": {"type": "int", "min": 300}
            },
            "buy_ten": {
                "default": 3000,
                "validator": {"type": "int", "min": 3000}
            },
        },
        "great_ball": {
            "buy_on_missing": {
                "default": True,
                "validator": {"type": "bool"}
            },
            "buy_one": {
                "default": 600,
                "validator": {"type": "int", "min": 600}
            },
            "buy_ten": {
                "default": 6000,
                "validator": {"type": "int", "min": 6000}
            },
        },
        "ultra_ball": {
            "buy_on_missing": {
                "default": True,
                "validator": {"type": "bool"}
            },
            "buy_one": {
                "default": 1000,
                "validator": {"type": "int", "min": 1000}
            },
            "buy_ten": {
                "default": 10000,
                "validator": {"type": "int", "min": 10000}
            },
        },
    },
    "catch": {
        "treat_uncapt_as_capt": {
            "default": False,
            "validator": {"type": "bool"}
        },
        "uncapt_S": {
            "default": uncapt_S_default,
            "validator": {"type": "str_list", "accepted_values": POKE_BALLS_LIST}
        },
        "S": {
            "default": S_default,
            "validator": {"type": "str_list", "accepted_values": POKE_BALLS_LIST}
        },
        "uncapt_M": {
            "default": uncapt_M_default,
            "validator": {"type": "str_list", "accepted_values": POKE_BALLS_LIST}
        },
        "M": {
            "default": M_default,
            "validator": {"type": "str_list", "accepted_values": POKE_BALLS_LIST}
        },
        "uncapt_A": {
            "default": uncapt_A_default,
            "validator": {"type": "str_list", "accepted_values": POKE_BALLS_LIST}
        },
        "A": {
            "default": A_default,
            "validator": {"type": "str_list", "accepted_values": POKE_BALLS_LIST}
        },
        "uncapt_B": {
            "default": uncapt_B_default,
            "validator": {"type": "str_list", "accepted_values": POKE_BALLS_LIST}
        },
        "B": {
            "default": B_default,
            "validator": {"type": "str_list", "accepted_values": POKE_BALLS_LIST}
        },
        "uncapt_C": {
            "default": uncapt_C_default,
            "validator": {"type": "str_list", "accepted_values": POKE_BALLS_LIST}
        },
        "C": {
            "default": C_default,
            "validator": {"type": "str_list", "accepted_values": POKE_BALLS_LIST}
        },
    },
    "stats_balls": {
        "heavy_ball": {
            "default": 200,
            "validator": {"type": "int", "min": 100}
        },
        "feather_ball": {
            "default": 50,
            "validator": {"type": "int", "min": 0, "max": 100}
        },
        "heal_ball": {
            "default": 100,
            "validator": {"type": "int", "min": 100}
        },
        "fast_ball": {
            "default": 150,
            "validator": {"type": "int", "min": 100}
        }
    },
    "discord": {
        "enabled": {
            "default": False,
            "validator": {"type": "bool"}
        },
        "webhook_url": {
            "default": "",
            "validator": {"type": "str"}
        },
        "ping_user": {
            "default": False,
            "validator": {"type": "bool"}
        }
    }
}
