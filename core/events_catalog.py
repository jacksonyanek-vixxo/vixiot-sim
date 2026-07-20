"""Mastrena II EventMaster catalog (73 events)."""

SEVERITY_RANK = {"Info": 0, "Warning": 1, "Error": 2, "Fatal": 3}

CATALOG = {
    0: ("UndefinedError", "Fatal", "Machine Issue"),
    1: ("BoilerControllerOK", "Info", "Machine Issue"),
    2: ("BoilerControllerError", "Error", "Machine Issue"),
    3: ("BoilerAvailable", "Info", "Machine Issue"),
    4: ("BoilerNotAvailable", "Info", "Machine Issue"),
    5: ("BoilerEmpty", "Info", "Machine Issue"),
    6: ("BoilerFlushing", "Info", "Machine Issue"),
    7: ("BoilerFull", "Info", "Machine Issue"),
    8: ("StatusManagerOK", "Info", "Machine Issue"),
    9: ("StatusManagerError", "Error", "Machine Issue"),
    10: ("BeanHopperPresent", "Info", "Operational Issue"),
    11: ("BeanHopperMissing", "Error", "Operational Issue"),
    15: ("GroundsDrawerPresent", "Info", "Operational Issue"),
    16: ("GroundsDrawerMissing", "Error", "Operational Issue"),
    17: ("GroundsDrawerOK", "Info", "Operational Issue"),
    19: ("GroundsDrawerFull", "Error", "Operational Issue"),
    26: ("CleaningOK", "Info", "Cleaning"),
    27: ("CleaningRecommended", "Warning", "Cleaning"),
    28: ("CleaningRequired", "Error", "Cleaning"),
    29: ("ProductCancelled", "Info", "Operational Issue"),
    30: ("MotorPositionError", "Error", "Machine Issue"),
    31: ("CommunicationError", "Error", "Machine Issue"),
    32: ("ComponentError", "Error", "Machine Issue"),
    33: ("ConfigurationError", "Fatal", "Machine Issue"),
    34: ("WaterFlowError", "Error", "Machine Issue"),
    35: ("BrewChamberEmpty", "Error", "Operational Issue"),
    36: ("BrewChamberTooFull", "Error", "Machine Issue"),
    38: ("SafetyReedDuringProduct", "Error", "Operational Issue"),
    39: ("FirmwareUpdateRunning", "Info", "Machine Issue"),
    40: ("FirmwareUpdateDone", "Info", "Machine Issue"),
    43: ("FanOK", "Info", "Machine Issue"),
    44: ("FanFailure", "Fatal", "Machine Issue"),
    45: ("ServiceOk", "Info", "Operational Issue"),
    46: ("ServiceRecommended", "Warning", "Operational Issue"),
    47: ("ServiceRequired", "Error", "Operational Issue"),
    53: ("ExtractionTooSlow", "Info", "Machine Issue"),
    54: ("ExtractionTooFast", "Info", "Machine Issue"),
    55: ("SteamOutletAvailable", "Info", "Machine Issue"),
    56: ("SteamOutletNotAvailable", "Error", "Machine Issue"),
    113: ("CleaningKeyMissing", "Error", "Operational Issue"),
    114: ("CleaningTabletMissing", "Error", "Operational Issue"),
    115: ("CleaningTabletNotResolved", "Error", "Machine Issue"),
    133: ("HardwareSoftwareMismatch", "Fatal", "Machine Issue"),
    136: ("CleaningInformation", "Info", "Cleaning"),
    10000: ("GuiStartingUp", "Info", "Machine Issue"),
    10001: ("GuiStartedUp", "Info", "Machine Issue"),
    10002: ("GuiShutdown", "Info", "Machine Issue"),
    10003: ("RestoreCompletedSuccessfully", "Info", "Machine Issue"),
    10004: ("GuiCleaningReady", "Info", "Cleaning"),
    10005: ("GuiCleaningNotReady", "Info", "Cleaning"),
    10006: ("GuiCleaningFinished", "Info", "Cleaning"),
    10007: ("GuiCleaningAbortedByUser", "Info", "Cleaning"),
    10008: ("GuiCleaningAbortedThroughError", "Info", "Cleaning"),
    10010: ("BackupRestoreError", "Error", "Machine Issue"),
    10013: ("MachineControlStartupFailure", "Fatal", "Machine Issue"),
    10014: ("MachineControlRegisterProductFailure", "Fatal", "Machine Issue"),
    10015: ("RtcBatteryEmpty", "Error", "Machine Issue"),
    10017: ("SwUpdateSuccess", "Info", "Machine Issue"),
    10022: ("EnergyModeReady", "Info", "Operational Issue"),
    10023: ("EnergyModeRest", "Info", "Operational Issue"),
    10024: ("EnergyModeDeepSleep", "Info", "Operational Issue"),
    10025: ("PoweredOn", "Info", "Machine Issue"),
    10026: ("SystemStartingUp", "Info", "Machine Issue"),
    10027: ("SystemReady", "Info", "Machine Issue"),
    10028: ("UserLogin", "Info", "Operational Issue"),
    10029: ("RecipeUpdateSuccess", "Info", "Machine Issue"),
    10030: ("RecipeUpdateFailed", "Error", "Machine Issue"),
    10031: ("TimeTainted", "Error", "Machine Issue"),
    10032: ("RinseRequired", "Info", "Machine Issue"),
    10036: ("SdCardAvailable", "Info", "Machine Issue"),
    10037: ("SdCardNotAvailable", "Fatal", "Machine Issue"),
    20001: ("Device connected", "Info", "Connectivity Events"),
    20002: ("Device disconnected", "Error", "Connectivity Events"),
}

# raise event number -> clear event number
PAIRS = {
    2: 1,
    4: 3,
    9: 8,
    11: 10,
    16: 15,
    19: 17,
    27: 26,
    28: 26,
    30: 43,
    31: 43,
    32: 43,
    34: 55,
    44: 43,
    46: 45,
    47: 45,
    56: 55,
    10005: 10004,
    10030: 10029,
    10037: 10036,
    20002: 20001,
}

MODULE_HINT = {
    0: "StatusManager",
    1: "BoilerController",
    2: "BoilerController",
    3: "BoilerController",
    4: "BoilerController",
    5: "BoilerController",
    6: "BoilerController",
    7: "BoilerController",
    8: "StatusManager",
    9: "StatusManager",
    10: "Grinder1",
    11: "Grinder1",
    15: "GroundsDrawer1",
    16: "GroundsDrawer1",
    17: "GroundsDrawer1",
    19: "GroundsDrawer1",
    26: "CleaningDispatcher",
    27: "CleaningDispatcher",
    28: "CleaningDispatcher",
    29: "ProductManager",
    30: "Grinder1",
    31: "CoffeeModule1",
    32: "CoffeeModule1",
    33: "StatusManager",
    34: "CoffeeModule1",
    35: "CoffeeModule1",
    36: "CoffeeModule1",
    38: "ProductManager",
    39: "Gui",
    40: "Gui",
    43: "CoffeeModule1",
    44: "CoffeeModule1",
    45: "OperationProcessor",
    46: "OperationProcessor",
    47: "OperationProcessor",
    53: "CoffeeModule1",
    54: "CoffeeModule1",
    55: "SteamManager",
    56: "SteamManager",
    113: "CleaningDispatcher",
    114: "CleaningDispatcher",
    115: "CleaningDispatcher",
    133: "StatusManager",
    136: "CleaningDispatcher",
    10000: "Gui",
    10001: "Gui",
    10002: "Gui",
    10003: "Gui",
    10004: "CleaningDispatcher",
    10005: "CleaningDispatcher",
    10006: "CleaningDispatcher",
    10007: "CleaningDispatcher",
    10008: "CleaningDispatcher",
    10010: "Gui",
    10013: "StatusManager",
    10014: "ProductManager",
    10015: "StatusManager",
    10017: "Gui",
    10022: "Gui",
    10023: "Gui",
    10024: "Gui",
    10025: "Gui",
    10026: "Gui",
    10027: "Gui",
    10028: "UserManager",
    10029: "Gui",
    10030: "Gui",
    10031: "StatusManager",
    10032: "CoffeeModule1",
    10036: "StatusManager",
    10037: "StatusManager",
    20001: "StatusManager",
    20002: "StatusManager",
}

MULTI_INSTANCE = {
    "GroundsDrawer": ("GroundsDrawer1", "GroundsDrawer2"),
    "Grinder": ("Grinder1", "Grinder2", "Grinder3"),
    "CoffeeModule": ("CoffeeModule1", "CoffeeModule2"),
}

FAULT_EVENT_MAP = {
    "pump_degradation": 34,
    "clogged_group": 32,
    "grinder_wear": 30,
    "heater_degradation": 2,
}

CATEGORIES = (
    "Cleaning",
    "Connectivity Events",
    "Machine Issue",
    "Operational Issue",
)

# Stochastic Info events by category (event numbers)
STOCHASTIC_INFO = {
    "Machine Issue": (6, 7, 53, 54, 10025, 10027),
    "Operational Issue": (29, 10022, 10023),
    "Cleaning": (136, 10006),
    "Connectivity Events": (),
}


def lookup(number):
    return CATALOG.get(number)


def clear_number(raise_number):
    return PAIRS.get(raise_number)


def is_stateful(number):
    return number in PAIRS or number in PAIRS.values()


def pairing_group(number):
    if number in PAIRS:
        return PAIRS[number]
    for raise_num, clear_num in PAIRS.items():
        if clear_num == number:
            return clear_num
    return number


def resolve_module(number, rng=None):
    hint = MODULE_HINT.get(number, "Gui")
    for prefix, choices in MULTI_INSTANCE.items():
        if hint.startswith(prefix.replace("Module", "")) or hint in choices:
            if rng is not None:
                return choices[int(rng.random() * len(choices)) % len(choices)]
            return choices[0]
    if hint == "GroundsDrawer1" and rng is not None:
        choices = MULTI_INSTANCE["GroundsDrawer"]
        return choices[int(rng.random() * len(choices)) % len(choices)]
    return hint
