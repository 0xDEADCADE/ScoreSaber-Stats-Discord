#!/usr/bin/env python3
# ScoreSaber Stats Bot, developed by 0xDEADCADE
# ScoreSaber Stats Bot is a Discord bot that sends updates about statistics on ScoreSaber users
import discord
import json
import random
import requests
import asyncio

# Important notes for maintainers
# Umbranox does not like API requests
# Discord throws away DM channels once every couple weeks, so we don't allow them to prevent a bunch of improper requests going to Discord
# This whole script is pretty garbage, I would've said you could start from scratch, but it's decent-ish now.
# ScoreSaber API has a massive ratelimit, like 50 requests per 25 minutes or something insane like that.
# ^ I've never measured it, but you're better off not doing too much more than this.
# ^ This is *per IP*. If you host this bot at home, and try to play beat saber, good luck uploading scores. ScoreSaber UI will be slow.
# ScoreSaber API is inconsistent with datatypes. ***Always*** convert if anything could error on incorrect datatype.
# ^ Expect String, Int, Float, and None(/null) to be mixed randomly.
# ^ I might've caused some of the datatype juggling as well

# Indicate whether the bot has been started yet.
StatUpdateRunning = False
StatusUpdateRunning = False
# Indicate whether currently the stats are being updated
IsUpdating = False

# Imported Variables
with open("Settings.json", "r") as f:
    Settings = json.loads(f.read())

HelpMessages = Settings["HelpMessages"]
StatusMessages = Settings["StatusMessages"]
Changelog = Settings["ChangeLog"]
Token = Settings["Token"]
SupportServer = Settings["SupportServerURL"]
ProfilePicture = Settings["PFPURL"]
SourceURL = Settings["SourceURL"]


# Functions
# Checks if user input values is yes or no
def IsYes(text):
    return "y" in text.lower() or "true" in text.lower()

# Checks if number is within number range of other number
def CheckThreshold(num, newnum, threshold):
    return abs(num - newnum) >= threshold

# Gets the scoreboard number for a specific rank
def GetScoreBoardNum(rank):
    # Used to use the entire math module for just this bit
    # return math.ceil(rank / 50)
    return int(rank / 50) + (rank % 50 > 0)

# Does an API call and should (but doesn't) handle errors with ScoreSaber API
def ApiCall(url):
    headers = {"User-Agent": "ScoreSaber Stats Bot", "From": SourceURL}
    r = requests.get(url, allow_redirects=True, headers=headers)
    return r.text

# Gets a profile from a scoresaber name
def GetSSProfileName(text):
    url = f"https://new.scoresaber.com/api/players/by-name/{text}"
    SearchData = json.loads(ApiCall(url))
    if "error" in SearchData.keys():
        raise KeyError
    return SearchData["players"][0]

# Gets a profile from ScoreSaber
def GetSSProfileAll(ssplayer):
    player = {}
    # Set ssid to 0 for checking if it was set
    ssid = 0
    # If this is a scoresaber url
    if "scoresaber.com" in str(ssplayer):
        # Try to int() each part
        for urlpart in ssplayer.split("/"):
            if not urlpart == "":
                try:
                    ssid = int(urlpart.split("&")[0].split("#")[0])
                except:
                    pass
    else:
        # Try to directly convert the id to an int
        try:
            ssid = int(ssplayer)
        except:
            pass
        # Not a link or a user id, check if a player of this name exists
        player = GetSSProfileName(ssplayer)
    # No ID was found and the player does not exist
    if ssid == 0 and player == {}:
        raise KeyError
    # No player was found but an ID was found
    if player == {} and ssid != 0:
        try:
            player = GetStatsID(ssid)
        except:
            raise KeyError
    else:
        return player

# Take a scoresaber id and check if the profile exists
def CheckIfSSIDExists(ssid):
    url = f"https://new.scoresaber.com/api/player/{ssid}/basic"
    # Request the URL and load it in as a JSON dict
    try:
        PlayerData = json.loads(ApiCall(url))
    except:
        return False
    # If scoresaber throws an error, we return False, else we return True
    return "error" not in PlayerData

# Get Default Embed
def GetEmbed(title, text):
    return discord.Embed(title=title, type="rich", description=text, color=discord.colour.Color.from_rgb(255, 222, 26)).set_footer(icon_url=ProfilePicture, text="ScoreSaber Stats")

# Same as above, but adds the support server link to the bottom of the embed text
def GetEmbedWithSupportLink(title, text):
    return GetEmbed(title, text + f"\n[Support Server]({SupportServer})")

# Gets a players stats assuming they exist and on ID only (for reducing API requests)
def GetStatsID(SSID):
    # Request the users profile
    url = f"https://new.scoresaber.com/api/player/{str(SSID)}/basic"
    PlayerData = json.loads(ApiCall(url))
    # Removes unnecesary dict layer
    PlayerData = PlayerData["playerInfo"]
    # ScoreSaber is inconsistent on the roles, it might be "", it might be None. So we set it to "" if it's None
    # If it's got content, set it to whatever the role is supposed to be
    PlayerData["avatar"] = "https://new.scoresaber.com" + PlayerData["avatar"]
    PlayerData["role"] = "" if PlayerData["role"] == "" or PlayerData["role"] is None else PlayerData["role"]
    return PlayerData

# Gets a random player off ScoreSaber leaderboards (from leaderboards 1 to 100, player rank 1 to 5000)
def GetRandomPlayer():
    url = "https://new.scoresaber.com/api/players/" + str(random.randint(1, 100))
    leaderboard = json.loads(ApiCall(url))["players"]
    return leaderboard[random.randint(0, 49)]

# Gets the person currently on #1 global
def GetNumberOneGlobal():
    url = "https://new.scoresaber.com/api/players/1"
    return json.loads(ApiCall(url))["players"][0]

# Randomly picks a status message
def GetStatus():
    return random.choice(StatusMessages)

# Updates the status message
async def UpdateStatus(client):
    # Probability for status messages
    # 3/7 message
    # 2/7 random player
    # 2/7 first player on leaderboards
    # There's probably a much better way of doing this.
    choice = random.choice([1, 1, 1, 2, 2, 3, 3])
    statustext = ""
    if choice == 1:
        statustext = GetStatus()
    elif choice == 2:
        player = GetNumberOneGlobal()
    elif choice == 3:
        player = GetRandomPlayer()
    if statustext == "":
        statustext = f"#{str(player['rank'])}: {player['playerName']} with {str(player['pp'])}pp"
    await client.change_presence(activity=discord.Game(name=f"{statustext} | SS!Help"))

# Function to send everyone updates about their stats
async def SendStatUpdates():
    global IsUpdating
    global ProfilePicture
    # Make sure to tell other commands it's updating the stats
    IsUpdating = True
    # Cache messages before sending to not mess up updating stats when discord is down
    Messages = []
    with open("SSData.json", "r+") as f:
        RegisteredPlayers = json.loads(f.read())
    for n, Player in enumerate(RegisteredPlayers):
        # Wait a bit here, Umbranox hates mass API usage
        await asyncio.sleep(3)
        NewPlayer = GetStatsID(Player["playerInfo"]["playerId"])
        # This code is bad
        # It creates 3 bools indicating that stats go beyond ranges the user has defined
        CountryRankCheck = CheckThreshold(int(Player["playerInfo"]["countryRank"]), int(NewPlayer["countryRank"]), int(Player["countryRankThreshold"]))
        GlobalRankCheck = CheckThreshold(int(Player["playerInfo"]["rank"]), int(NewPlayer["rank"]), int(Player["globalRankThreshold"]))
        PPCheck = CheckThreshold(float(Player["playerInfo"]["pp"]), float(NewPlayer["pp"]), float(Player["ppThreshold"]))
        # Then it checks if any of those are true
        if CountryRankCheck or GlobalRankCheck or PPCheck:
            try:
                # Try to get the channel from cache
                UpdateChannel = client.get_channel(int(Player["channelId"]))
            except:
                # If it fails in any way, just move on to the next player
                continue
            if UpdateChannel == None:
                # Discord.py likes to randomly return None instead of throwing an error
                continue
            
            # If the user has selected to be pinged on status update
            if Player["ping"]:
                ping = f"<@{Player['discordUserId']}> "
            else:
                ping = ""
            MessageText = ping + NewPlayer["playerName"] + "'s stats have changed!"
            # If the player transitions from active to inactive
            if int(Player["playerInfo"]["inactive"]) == 0 and NewPlayer["inactive"] == 1:
                MessageText += f"\n{Player['playerInfo']['playerName']} has been listed as inactive!"
            # If the player transitions from normal to banned
            if int(Player["playerInfo"]["banned"]) == 0 and NewPlayer["banned"] == 1:
                MessageText += f"\n{Player['playerInfo']['playerName']} has been listed as banned!"
            # + if rank went up, - if rank went down, "" if rank is the same
            GlobalIndicator = "+" if int(Player["playerInfo"]["rank"]) - int(NewPlayer["rank"]) > 0 else "-" if int(NewPlayer["rank"]) - int(Player["playerInfo"]["rank"]) > 0 else ""
            CountryIndicator = "+" if int(Player["playerInfo"]["countryRank"]) - int(NewPlayer["countryRank"]) > 0 else "-" if int(NewPlayer["countryRank"]) - int(Player["playerInfo"]["countryRank"]) > 0 else ""
            PPIndicator = "+" if float(Player["playerInfo"]["pp"]) - float(NewPlayer["pp"]) < 0 else "-" if float(Player["playerInfo"]["pp"]) - float(NewPlayer["pp"]) > 0 else ""
            # Embed text
            MessageEmbedText = f"Global Rank: `#{Player['playerInfo']['rank']}>#{NewPlayer['rank']}` (`{GlobalIndicator}{abs(Player['playerInfo']['rank'] - NewPlayer['rank'])}`)\nCountry Rank (:flag_{NewPlayer['country'].lower()}:{NewPlayer['country']}): `#{Player['playerInfo']['countryRank']}>#{NewPlayer['countryRank']}` (`{CountryIndicator}{abs(Player['playerInfo']['countryRank'] - NewPlayer['countryRank'])}`)\nPP: `{Player['playerInfo']['pp']}pp>{NewPlayer['pp']}pp` (`{PPIndicator}{abs(round(NewPlayer['pp'] - float(Player['playerInfo']['pp']), 2))}`)\nLeaderboards: [Global](https://scoresaber.com/global/{str(GetScoreBoardNum(NewPlayer['rank']))}) | [Country](https://scoresaber.com/global/{str(GetScoreBoardNum(NewPlayer['countryRank']))}&country={NewPlayer['country'].lower()})"
            # Full embed object
            MessageEmbed = GetEmbed("", MessageEmbedText).set_author(name=NewPlayer['playerName'], url=f"https://scoresaber.com/u/{Player['playerInfo']['playerId']}", icon_url=NewPlayer['avatar']).set_footer(icon_url=ProfilePicture, text=f"ID: {Player['playerInfo']['playerId']}")
            # Append message for later use
            Messages.append([UpdateChannel, MessageText, MessageEmbed])
            Player["playerInfo"] = NewPlayer
            # Overwrite player data
            RegisteredPlayers[n] = Player
    with open("SSData.json", "w+") as f:
        f.write(json.dumps(RegisteredPlayers, indent=4))

    # After updating all the players stats and saving them to a file, send messages
    for message in Messages:
        # Wait a couple seconds per update, discord doesn't like spamming
        await asyncio.sleep(2)
        try:
            channel = message[0]
            await channel.send(message[1], embed=message[2])
        except:
            pass
    # Tell commands updating process is done
    IsUpdating = False

# Update stats on a time interval
async def StatUpdateRoutine():
    global StatUpdateRunning
    global IsUpdating
    await client.wait_until_ready()
    StatUpdateRunning = True
    while True:
        try:
            await SendStatUpdates()
        except Exception as ex:
            print(ex)
        IsUpdating = False
        # Update stats once every 30 minutes
        await asyncio.sleep(1800)

# Update discord bot status on a time interval
async def StatusUpdateRoutine():
    global StatusUpdateRunning
    await client.wait_until_ready()
    StatusUpdateRunning = True
    while True:
        try:
            await UpdateStatus(client)
        except Exception as ex:
            print(ex)
        # Update status once every 10 minutes
        await asyncio.sleep(600)

class MyClient(discord.Client):

    async def on_ready(self):
        global StatUpdateRunning
        global StatusUpdateRunning
        print(f"Logged in as {str(self.user)}")
        if not StatUpdateRunning:
            bg_task = client.loop.create_task(StatUpdateRoutine())
        if not StatusUpdateRunning:
            bg_task2 = client.loop.create_task(StatusUpdateRoutine())

    async def on_message(self, message):
        global IsUpdating
        global HelpMessages
        global Changelog
        global SupportServer
        global ProfilePicture
        global SourceURL
        # If any bot sends a message
        if message.author.bot:
            return
        # If the message is not a command
        if not message.content.lower().startswith("ss!"):
            return
        # Send link to license
        if message.content.lower() == "ss!license":
            await message.channel.send("https://www.gnu.org/licenses/gpl-3.0.txt")
        # Help command
        if message.content.lower().startswith("ss!help"):
            splitcontent = message.content.split(" ")
            if len(splitcontent) == 1:
                # No command specified, send command list
                await message.channel.send(content="", embed=GetEmbedWithSupportLink("Command List", HelpMessages["help"] + f"\n[Source Code]({SourceURL})"))
            elif len(splitcontent) == 2:
                HelpString = splitcontent[1].split("!")[-1].lower()
                if HelpString in HelpMessages.keys():
                    await message.channel.send(content="", embed=GetEmbed("SS!{HelpString[0].upper()}{HelpString[1:]}", HelpMessages[HelpString]))
                else:
                    await message.channel.send("Unknown command!")

        # Get info about a user
        if message.content.lower().startswith("ss!info"):
            # Split arguments
            splitcontent = message.content.split(" ")
            # If no arguments are given
            if len(splitcontent) < 2:
                await message.channel.send("Please provide a ScoreSaber Name, UID, or URL!\nExamples: `SS!Info https://scoresaber.com/u/76561198161040596`\n`SS!Info Taichidesu`")
                return
            # Catch KeyError (thrown by GetPlayerProfileAll and passed by GetStats)
            try:
                player = GetSSProfileAll(' '.join(splitcontent[1:]))
            except KeyError:
                await message.channel.send("That user doesn't exist!")
                return
            # Send the message
            await message.channel.send(content="", embed=GetEmbed("", f"Global Rank: `#{str(player['rank'])}`\nCountry Rank (:flag_{player['country'].lower()}:{player['country']}): `#{str(player['countryRank'])}`\nPP: `{str(player['pp'])}pp`\nLeaderboards: [Global](https://scoresaber.com/global/{str(GetScoreBoardNum(player['rank']))}) | [Country](https://scoresaber.com/global/{str(GetScoreBoardNum(player['countryRank']))}&country={player['country'].lower()})").set_author(name=player['playerName'], url=f"https://scoresaber.com/u/{player['playerId']}", icon_url=player["avatar"]).set_footer(icon_url=ProfilePicture, text=f"ID: {player['playerId']}"))
            return
        
        # Register command
        if message.content.lower().startswith("ss!register"):
            # If the stats are being updated
            if IsUpdating:
                await message.channel.send("Sorry, the bot is currently updating everyone's stats. Please try again in a minute.")
                return
            # If in DMs
            if message.channel.type == "private":
                await message.channel.send("DM support is disabled. Ask in the support server for more info")
                return
            splitcontent = message.content.split(" ")
            # If no arguments were provided
            if len(splitcontent) < 2:
                await message.channel.send("Please provide a ScoreSaber Name, UID, or URL!\nExamples: `SS!Register https://scoresaber.com/u/76561198333869741`\n`SS!Register Taichidesu`")
                return
            # Catch keyerror for non-existant user
            try:
                player = GetSSProfileAll(splitcontent[1])
                # We *have* to re-request information here.
                # Player data by name search does not get the same info as /basic endpoint
                # Since it's only required here (during checkups we use ID), we only re-request here.
                player = GetStatsID(player["playerId"])
            except KeyError:
                await message.channel.send("That user doesn't exist!")
                return
            with open("SSData.json", "r+") as f:
                FullData = json.loads(f.read())
            for RegisteredPlayer in FullData:
                if RegisteredPlayer["channelId"] == message.channel.id and RegisteredPlayer["discordUserId"] == message.author.id and RegisteredPlayer["playerInfo"]["playerId"] == player["playerId"]:
                    await message.channel.send("This player is already registered!")
                    return
            # Default settings
            ping = True
            GlobalRankThreshold = 1
            CountryRankThreshold = 1
            PPThreshold = 0.01
            # Parse settings (Hello r/badcode!)
            for n, arg in enumerate(splitcontent):
                # SS!Register (player) (args)
                # If we're at the args
                if n > 1:
                    # Split the argument name
                    try:
                        argname = arg.split("=")[0]
                        argvalue = arg.split("=")[1]
                    except:
                        # If it was broken somehow, like invalid syntax, just move on to the next arg.
                        continue
                    if argname == "ping":
                        # Check if the user supplied "Yes", "True" or any variation of those
                        ping = IsYes(argvalue)
                    elif argname == "globalRankThreshold":
                        # Catch exception if argument value isn't a valid integer
                        try:
                            GlobalRankThreshold = int(argvalue)
                            # If the threshold is below 0, it triggers every update.
                            if GlobalRankThreshold <= 0:
                                await message.channel.send("Wrong value for globalRankThreshold! Must be more than 0!")
                                return
                        except:
                            await message.channel.send("Wrong value for globalRankThreshold! Must be a number!")
                            return
                    elif argname == "countryRankThreshold":
                        try:
                            CountryRankThreshold = int(argvalue)
                            if CountryRankThreshold <= 0:
                                await message.channel.send("Wrong value for countryRankThreshold! Must be more than 0!")
                                return
                        except:
                            await message.channel.send("Wrong value for countryRankThreshold! Must be a number!")
                            return
                    elif argname == "ppThreshold":
                        try:
                            PPThreshold = float(argvalue)
                            if PPThreshold <= 0.0:
                                await message.channel.send("Wrong value for ppThreshold! Must be more than 0!")
                                return
                        except:
                            await message.channel.send("Wrong value for ppThreshold! Must be a number!")
                            return
                    else:
                        await message.channel.send(f"Unknown Argument `{argname}`!")
                        return
            # Add the new player into the list
            NewPlayer = {"playerInfo": player, "channelId": message.channel.id, "discordUserId": message.author.id, "ping": ping, "globalRankThreshold": GlobalRankThreshold, "countryRankThreshold": CountryRankThreshold, "ppThreshold": PPThreshold}
            with open("SSData.json", "w+") as f:
                FullData.append(NewPlayer)
                f.write(json.dumps(FullData, indent=4))
            # Notify the user of it being added
            await message.channel.send(f"{message.author.mention} You will get notified in this channel when {NewPlayer['playerInfo']['playerName']}'s rank or pp changes.\nSettings:\n`Ping`: `{'Yes' if ping else 'No'}`\n`Global Rank Threshold`: `{GlobalRankThreshold}`\n`Country Rank Threshold`: `{CountryRankThreshold}`\n`PP Threshold`: `{PPThreshold}`")
            return

        if message.content.lower().startswith("ss!unregister"):
            if IsUpdating:
                await message.channel.send("Sorry, the bot is currently updating everyone's stats. Please try again in a minute.")
                return
            splitcontent = message.content.split(" ")
            # If no name, id, or url was provided
            if len(splitcontent) < 2:
                await message.channel.send("Please provide a ScoreSaber Name, UID, or URL!\nExamples: `SS!UnRegister https://scoresaber.com/u/76561198333869741`\n`SS!UnRegsiter Taichidesu`")
                return
            # Get player stats on everything after the command
            try:
                player = GetSSProfileAll(' '.join(splitcontent[1:]))
            except KeyError:
                await message.channel.send("That player doesn't exist!")
                return
            with open("SSData.json", "r+") as f:
                FullData = json.loads(f.read())
            # Remove the player in this channel by this user with the given player id
            for RegisteredPlayer in FullData:
                if RegisteredPlayer["channelId"] == message.channel.id and RegisteredPlayer["discordUserId"] == message.author.id and RegisteredPlayer["playerInfo"]["playerId"] == str(player["playerId"]):
                    FullData.remove(RegisteredPlayer)
                    with open("SSData.json", "w+") as f:
                        f.write(json.dumps(FullData, indent=4))
                        await message.channel.send(f"{message.author.mention} You will no longer get notified in this channel when {RegisteredPlayer['playerInfo']['playerName']}'s rank or pp changes.")
                    return
            # No return means we didn't find anything at this point
            await message.channel.send("That player is not registered in this channel!")
            return

        if message.content.lower() == "ss!list":
            # Read the player data
            with open("SSData.json", "r+") as f:
                FullData = json.loads(f.read())
            # Create a list of players in this channel
            registered = []
            for RegisteredPlayer in FullData:
                if RegisteredPlayer["channelId"] == message.channel.id and RegisteredPlayer["discordUserId"] == message.author.id:
                    registered.append(RegisteredPlayer)
            embeds = []
            if len(registered) > 0:
                text = ""
                # Create a list of embeds to send with player profile links and data
                for Player in registered:
                    playerText = f"#{str(Player['playerInfo']['rank'])} :flag_{Player['playerInfo']['country'].lower()}:[{Player['playerInfo']['playerName']}](https://scoresaber.com/u/{Player['playerInfo']['playerId']}) | {str(Player['playerInfo']['pp'])}pp\n"
                    if len(text + playerText) < 2000:
                        text += playerText
                    else:
                        embeds.append(GetEmbed("Registered users in this channel", text))
                        text = playerText
                embeds.append(GetEmbed("Registered users in this channel", text))
                # Send the embeds to the channel
                for embed in embeds:
                    await asyncio.sleep(1)
                    await message.channel.send(content="", embed=embed)
            else:
                await message.channel.send("No registered users in this channel!")
            return

        if message.content.lower().startswith("ss!leaderboard"):
            splitcontent = message.content.split(" ")
            if len(splitcontent) < 2:
                await message.channel.send(f"Please provide a global leaderboard position!\nExample: `SS!Leaderboard 25`")
                return
            try:
                rank = int(splitcontent[1])
                if rank < 1:
                    await message.channel.send("Please provide a valid rank!")
                    return
            except:
                await message.channel.send("Please provide a valid rank!")
                return
            # Get the leaderboard the user requested for
            url = f"https://new.scoresaber.com/api/players/{str(GetScoreBoardNum(rank))}"
            leaderBoard = json.loads(ApiCall(url))
            # If rank is greater than or equal to 7.
            # Because if it's 4 for example, rank - 5 would give -1 rank position, and thus -1 leaderboard. Requesting that errors.
            if rank >= 7:
                # If rank - 5 is on a different leaderboard number
                if GetScoreBoardNum(rank - 5) != GetScoreBoardNum(rank):
                    # Get that leaderboard
                    url = f"https://new.scoresaber.com/api/players/{GetScoreBoardNum(rank - 5)}"
                    tmpLeaderBoard = json.loads(ApiCall(url))
                    # Add the first leaderboard to the end of the new one
                    tmpLeaderBoard["players"].extend(leaderBoard["players"])
                    # Set the old leaderboard to the new one
                    leaderBoard = tmpLeaderBoard
                # If rank + 5 is on a different leaderboard number
                elif GetScoreBoardNum(rank + 5) != GetScoreBoardNum(rank):
                    # Get that leaderboard
                    url = f"https://new.scoresaber.com/api/players/{GetScoreBoardNum(rank + 5)}"
                    tmpLeaderBoard = json.loads(ApiCall(url))
                    # Add the new leaderboard to the end of the old one
                    leaderBoard["players"].extend(tmpLeaderBoard["players"])
            # Create the list of people near that leaderboard position
            text = ""
            heretext = ""
            # For every player in the grabbed leaderboards
            for player in leaderBoard["players"]:
                # Check if the player rank is within 5 of the given rank
                # This gives us 9 total players, with the requested one being in the middle
                if not CheckThreshold(int(player["rank"]), rank, 5):
                    # If the requested rank is this player
                    if player["rank"] == rank:
                        heretext = "**HERE** -> "
                    text += f"{heretext}#{player['rank']} :flag_{player['country'].lower()}:[{player['playerName']}](https://scoresaber.com/u/{player['playerId']}) | {player['pp']}pp\n"
                    heretext = ""
            # Add the leaderboard page link
            text += f"\n[Leaderboard Page](https://scoresaber.com/global/{GetScoreBoardNum(rank)})"
            try:
                # Send the message as an embed
                await message.channel.send(content="", embed=GetEmbed(f"Leaderboard near {rank}", text))
            except:
                # If the message was too long or discord doesn't like it
                await message.channel.send("Mesage could not be sent!")
                return

        if message.content.lower().startswith("ss!changelog"):
            splitcontent = message.content.split(" ")
            # If no version tag was given
            if len(splitcontent) == 1:
                await message.channel.send(content="", embed=GetEmbed(f"Changelog for {Changelog['Latest']}", Changelog[Changelog['Latest']]))
            else:
                # If a version tag was given, check if it exists
                if splitcontent[1] in Changelog.keys():
                    # Send the changelog
                    await message.channel.send(content="", embed=GetEmbed(f"Changelog for {splitcontent[1]}", Changelog[splitcontent[1]]))
                else:
                    # If the tag doesn't exist
                    text = ""
                    # Generate the versions list
                    for version in Changelog.keys():
                        if version == "Latest":
                            continue
                        text += f"`{version}` "
                    # Send the list of versions
                    await message.channel.send(f"Not a valid version!\nVersions:\n{text}")
            return

client = MyClient()
client.run(Token)
