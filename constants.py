HORSE_NUMBERS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

COMBINATIONS = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6,
                8: 5, 9: 4, 10: 3, 11: 2, 12: 1}

# Steps to reach finish: scales linearly with combinations (1→3, 6→17)
TRACK_LENGTHS = {n: round(COMBINATIONS[n] * 17 / 6) for n in HORSE_NUMBERS}
# {2:3, 3:6, 4:9, 5:11, 6:14, 7:17, 8:14, 9:11, 10:9, 11:6, 12:3}

HORSE_COLORS = {
    2:  '#E74C3C',
    3:  '#E67E22',
    4:  '#F4D03F',
    5:  '#27AE60',
    6:  '#1ABC9C',
    7:  '#2980B9',
    8:  '#8E44AD',
    9:  '#E91E8C',
    10: '#FF5722',
    11: '#00BCD4',
    12: '#B0BEC5',
}
