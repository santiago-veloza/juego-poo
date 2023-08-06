import socket
import threading
import time
import pickle
from models.player import Player

lock = threading.Lock()
clients_locked = False

boost = -1

# dictionary of connected clients
# {client_id, Player}
# Justin's Change: Changed Shotaro's conversion from list back to dictionary
clients = {}

# hard coded list of all implemented actions
actions = {}

# main server thread
def server_main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('localhost', 8080))
    server_socket.listen(2) # Set the backlog to 2 to allow two clients to connect.

    print("server listening on port 8080")

    # TODO
    # Still need to make sure there are 2 players are connected before starting - done
    # If theres only 1 player and they click "ready", game still starts - done

    # allow 2 clients to connect
    while True:
        try:
            client_socket, client_address = server_socket.accept()
            # Send the player count the the client for checking
            send_dictionary_length(client_socket, len(clients)) 

            if len(clients) < 2: # only two players are allowed to play
                print(f"Accepted connection from {client_address}")

                # create player entry in clients
                # Justin's Change: Changed Shotaro's conversion from list back to dictionary 
                p = Player(client_socket)
                clients[p.clientId] = p

                # serve client on seperate thread
                client_thread = threading.Thread(target=communicate_with_client, args=(client_socket, p.clientId))
                client_thread.start()
        except Exception as e:
            print(f"Error accepting client connection: {e}")    
    
    # close server socket
    server_socket.close()
    
# client thread
def communicate_with_client(client_socket, client_id):
    global boost
    while True:
        try:
            data = client_socket.recv(1024)
            if not data:
                break
            message = data.decode("utf-8")
                
            #split headers and payloads with :
            applicationMessage = message.split(":")

            # check headers and payloads
            msg_iterator = iter(applicationMessage)
            header = next(msg_iterator)

            # server request logic
            if header == "ready":
                msg = f"ready_display:{client_id}:Player {client_id} READY" # changed header from text to ready_display, also pass the client id 
                broadcast_message(msg)
                pokemon_index = applicationMessage[1]
                clients[client_id].usePokemon(int(pokemon_index))
                clients[client_id].ready = True
                ready_check()
            elif header == "attack":
                attack_name = next(msg_iterator)
                if next(msg_iterator) == "damage":
                    damage = next(msg_iterator)
                    print(f"{clients[client_id].battlePokemon.boosted_name if client_id == boost else clients[client_id].battlePokemon.name} used {attack_name}, dealing {damage} damage!")
                    process_attack(client_id, attack_name, damage)
            elif header == "boost":
                ## if enemy aready used boosting, the action locked 
                if boost == -1:
                   boost_my_pokemon(clients, client_id)
            elif header == "stop_boost":
                if boost != -1:
                   stop_boost_my_pokemon(clients, client_id)
            elif header == "return":
                boost = -1
                clients[client_id].battlePokemon.current_hp = clients[client_id].battlePokemon.hp 

        except Exception as e:
            print(f"Error handling client {client_id}: {e}")
            boost = -1
            break

    # close connection
    print(f"Client {client_id} disconnected.")
    clients.pop(client_id)
    client_socket.close()

# send message to all connected clients
def broadcast_message(message):
    try:
        keys = list(clients.keys())
        if message == "game_start":
            # if player1 and player2 use same pokemon, player1 get Mewtwo as a special pokemon
            if clients[keys[0]].battlePokemon == clients[keys[1]].battlePokemon:
                clients[keys[0]].usePokemon(10)
            pokemonMsg = pokemonMsg = f"pokemon:{pickle.dumps(clients[keys[0]].battlePokemon)}:{pickle.dumps(clients[keys[1]].battlePokemon)}"
            clients[keys[0]].sock.send(pokemonMsg.encode("utf-8"))
            pokemonMsg = pokemonMsg = f"pokemon:{pickle.dumps(clients[keys[1]].battlePokemon)}:{pickle.dumps(clients[keys[0]].battlePokemon)}"
            clients[keys[1]].sock.send(pokemonMsg.encode("utf-8"))
        clients[keys[0]].sock.send(message.encode("utf-8"))
        clients[keys[1]].sock.send(message.encode("utf-8"))
    except Exception as e:
        print("Error broadcasting message: ", {e})


# check if all players are ready before starting game
def ready_check():
    # check if all players are ready
    for player in clients.values():
        # Justin: Since we dont need to use getters/setters, replaced function called with class variable call
        if not player.ready:
            return
    # check if there are only 2 players 
    if len(clients) == 2:
        start_game()

# send the dictionary length/player count to the client so it knows whether to draws a new pygame window or not
def send_dictionary_length(client_socket, length):
    try:
        message = f"dictionary_length:{length}"
        client_socket.send(message.encode("utf-8"))
    except Exception as e:
        print(f"Error sending dictionary length to client: {e}")   

def start_game():
    broadcast_message("count_down:3")
    time.sleep(1)
    broadcast_message("count_down:2")
    time.sleep(1)
    broadcast_message("count_down:1")
    time.sleep(1)
    broadcast_message("count_down:GAME START")
    time.sleep(1)
    broadcast_message("game_start")

def process_attack(client_id, attack_name, damage):
    global clients_locked
    global boost

    opponent_id = 0

    # Should only ever be 2 clients at a time
    for key, value in clients.items():
        if key != client_id:
            opponent_id = key

    attacker = clients[client_id]
    opponent = clients[opponent_id]

    with lock:
        if clients_locked:
            attacker.sock.send("text:Waiting for other player to finish their turn".encode("utf-8"))
            return
        clients_locked = True
        broadcast_message("lock")

        actual_damage = int(damage)
        if opponent_id == boost:
            actual_damage *= 2
        opponent.battlePokemon.get_attacked(actual_damage)

        broadcast_message(f"log:{attacker.battlePokemon.boosted_name if client_id == boost else attacker.battlePokemon.name} used {attack_name}, dealing {actual_damage} damage!")

        # calculate new hp vals
        attacker_hp = attacker.battlePokemon.current_hp
        opponent_hp = opponent.battlePokemon.current_hp

        time.sleep(1)
        try:
            # Send hp updates to clients
            attacker.sock.send(f"hp_update:{attacker_hp}:{opponent_hp}".encode("utf-8"))
            opponent.sock.send(f"hp_update:{opponent_hp}:{attacker_hp}".encode("utf-8"))
        except Exception as error:
            print(error)
        time.sleep(1)
        
        #check if game is over
        if opponent.battlePokemon.current_hp <= 0:
            print("game over!")
            # Reset each player's ready state for future games
            attacker.ready = False
            opponent.ready = False
            # Send gameover messages
            attacker.sock.send("game_over:win".encode("utf-8"))
            opponent.sock.send("game_over:lose".encode("utf-8"))
        else:
            broadcast_message("unlock")

        clients_locked = False
        return
    
def boost_my_pokemon(clients, client_id):
    # Should only ever be 2 clients at a time
    global boost
    for key in clients.keys():
        if key != client_id:
             clients[key].sock.send("enemy_boost".encode("utf-8"))
        if key == client_id:
             boost = client_id
             clients[key].sock.send("boost".encode("utf-8"))

def stop_boost_my_pokemon(clients, client_id):
    global boost
    for key in clients.keys():
        if key != client_id:
            clients[key].sock.send("enemy_boost_end".encode("utf-8"))
        if key == client_id:
            clients[key].sock.send("boost_end".encode("utf-8"))
    boost = -1

if __name__ == "__main__":
    server_main()

