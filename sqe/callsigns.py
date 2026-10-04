"""DCS-native callsigns (ids verified against what pydcs/DCS assigns per aircraft type)."""
GENERIC = {"Enfield": 1, "Springfield": 2, "Uzi": 3, "Colt": 4, "Dodge": 5, "Ford": 6, "Chevy": 7, "Pontiac": 8}
EXTRA = {
    "FA-18C": {"Hornet": 9, "Squid": 10, "Ragin": 11, "Roman": 12, "Sting": 13, "Jury": 14, "Joker": 15, "Ram": 16,
               "Hawk": 17, "Devil": 18, "Check": 19, "Snake": 20},
    "F-16C": {"Viper": 9, "Venom": 10, "Lobo": 11, "Cowboy": 12, "Python": 13, "Rattler": 14, "Panther": 15,
              "Wolf": 16, "Weasel": 17, "Wild": 18, "Ninja": 19, "Jedi": 20},
    "A-10C": {"Hawg": 9, "Boar": 10, "Pig": 11, "Tusk": 12},
}
TANKER = {"Texaco": 1, "Arco": 2, "Shell": 3}
AWACS = {"Overlord": 1, "Magic": 2, "Wizard": 3, "Focus": 4, "Darkstar": 5}


def table(aircraft_key: str) -> dict:
    return {**GENERIC, **EXTRA.get(aircraft_key, {})}


def apply(group, name: str, flight_no: int, tbl: dict) -> list:
    """Set DCS callsigns on every unit: 'Springfield 1-2' = flight 1, aircraft 2. Returns the unit callsign strings."""
    out = []
    for i, u in enumerate(group.units, 1):
        u.callsign_dict = {1: tbl[name], 2: flight_no, 3: i, "name": f"{name}{flight_no}{i}"}
        out.append(f"{name} {flight_no}-{i}")
    return out
