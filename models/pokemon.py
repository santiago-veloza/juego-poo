class Pokemon:
    def __init__(self, name, ability):
        self.hp = 100
        self.current_hp = 100
        self.alive = True
        self.name = name
        self.ability = ability

    def get_attacked(self, damage):
        self.current_hp -= damage
