"""
MARIO.PY
###################################################################################
MIT License
Copyright (c) 2022 Bruno Hautzenberger, Jamin Kauf
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from .LEGO_MARIO_DATA import *
import asyncio
from bleak import BleakScanner, BleakClient, BleakError
from typing import Any, Callable, Iterable, Union


class Mario:

    def __init__(self, 
                doLog: bool=True, 
                accelerometerEventHooks: Union[
                    Callable[["Mario", int, int, int], Any], 
                    Iterable[Callable[["Mario", int, int, int], Any]]
                    ]=None,
                tileEventHooks: Union[
                    Callable[["Mario", str], Any], 
                    Iterable[Callable[["Mario", str], Any]]
                    ]=None, 
                pantsEventHooks: Union[
                    Callable[["Mario", str], Any], 
                    Iterable[Callable[["Mario", str], Any]]
                    ]=None, 
                logEventHooks: Union[
                    Callable[["Mario", str], Any], 
                    Iterable[Callable[["Mario", str], Any]]
                    ]=None,
                defaultVolume: Union[int, None]=None
                ) -> None:
        """Object to connect and control a single Lego Mario or Luigi.

        Args:
            doLog (bool, optional): Enables Logs to Stdout. Defaults to True.

            accelerometerEventHooks (Union[Callable, list], optional): Event Hook(s) that should be called every time new accelerometer data is received. 
                Functions need to take four inputs (sender: Mario, x: int, y: int, z: int). Defaults to None.

            tileEventHooks (Union[Callable, list], optional): Event Hook(s) that should be called every time new camera data is received. 
                Functions need to take two inputs: (sender: Mario, ground: str). Defaults to None.

            pantsEventHooks (Union[Callable, list], optional): Event Hook(s) that should be called every time new pants data is received. 
                Functions need to take two inputs: (sender: Mario, pants: str). Defaults to None.

            logEventHooks (Union[Callable, list], optional): Event Hook(s) that should be called every time something gets logged. 
                Functions need to take two inputs: (sender: Mario, msg: str). Defaults to None.
                
            defaultVolume (Union[int, None], optional): Volume (0-100) that should be set every time Mario reconnects. 
                If not provided, will not adjust volume. Defaults to None.
        """

        self._doLog = doLog # output logs to stdout only if True
        self._run = False
        self._autoReconnect = True  # if True, will try to reconnect as soon as disconnected
        self._client = None # bleak client
        self.defaultVolume = defaultVolume # volume to set Mario to after every connection. Default None won't change volume.

        # values to keep most recent event in memory
        self.pants: str = None
        self.ground: str = None
        self.acceleration: tuple[int, int, int] = None
        self.recentTile: str = None

        self._accelerometerEventHooks: list[
                                        Callable[
                                            [Mario, int, int, int],
                                            Any]
                                        ] = []
        self._tileEventHooks: list[Callable[[Mario, str], Any]] = []
        self._pantsEventHooks: list[Callable[[Mario, str], Any]] = []
        self._logEventHooks: list[Callable[[Mario, str], Any]] = []
        self.ALLHOOKS = (self._accelerometerEventHooks, self._pantsEventHooks,
                        self._tileEventHooks, self._logEventHooks)

        self.AddAccelerometerHook(accelerometerEventHooks)
        self.AddTileHook(tileEventHooks)
        self.AddPantsHook(pantsEventHooks)
        self.AddLogHook(logEventHooks)

        try: # if event loop exists, use that one
            asyncio.get_event_loop().create_task(self.connect())
        except RuntimeError: # otherwise, create a new one
            asyncio.set_event_loop(asyncio.SelectorEventLoop())
            asyncio.get_event_loop().create_task(self.connect())

    def _log(self, msg, end="\n"):
        """Log any message to stdout and call all assigned LogEvent handlers.

        Args:
            msg (object): Any printable object.
            end (str, optional): Same as end in print(). Defaults to "\n".
        """
        for func in self._logEventHooks:
            func(self, msg)
        if self._doLog:
            address = "Not Connected" if not self._client else self._client.address
            print((f"\r{address}: {msg}").ljust(100), end=end)

    def AddLogHook(
        self, 
        funcs: Union[
            Callable[["Mario", str], Any], 
            Iterable[Callable[["Mario", str], Any]]]
        ) -> None:
        """Adds function(s) as event hooks for updated tile or color values.

        Args:
            funcs (function or list of functions): function or list of functions that take (Mario, str) as input.
        """
        if callable(funcs):
            self._logEventHooks.append(funcs)
        elif hasattr(funcs, '__iter__'):
            for hook_function in funcs:
                self.AddLogHook(hook_function)

    def AddTileHook(
        self, 
        funcs: Union[
            Callable[["Mario", str], Any], 
            Iterable[Callable[["Mario", str], Any]]]
        ) -> None:
        """Adds function(s) as event hooks for updated tile or color values.

        Args:
            funcs (Union[Callable[["Mario", str], Any], Iterable[Callable[["Mario", str], Any]]]): function or list of functions that take (Mario, str) as input.
        """
        if callable(funcs):
            self._tileEventHooks.append(funcs)
        elif hasattr(funcs, '__iter__'):
            for hook_function in funcs:
                self.AddTileHook(hook_function)

    def AddAccelerometerHook(
        self, 
        funcs: Union[
            Callable[["Mario", int, int, int], Any], 
            Iterable[Callable[["Mario", int, int, int], Any]]]
        ) -> None:
        """Adds function(s) as event hooks for updated accelerometer values.

        Args:
            funcs (function or list of functions): function or list of functions that take (Mario, int, int, int) as input.
        """
        if callable(funcs):
            self._accelerometerEventHooks.append(funcs)
        elif hasattr(funcs, '__iter__'):
            for hook_function in funcs:
                self.AddAccelerometerHook(hook_function)

    def AddPantsHook(
        self, 
        funcs: Union[
            Callable[["Mario", str], Any], 
            Iterable[Callable[["Mario", str], Any]]]
        ) -> None:
        """Adds function(s) as event hooks for updated pants values.

        Args:
            funcs (function or list of functions): function or list of functions that take a Mario object and a single string as input.
        """
        if callable(funcs):
            self._pantsEventHooks.append(funcs)
        elif hasattr(funcs, '__iter__'):
            for hook_function in funcs:
                self.AddPantsHook(hook_function)
        
        
    def RemoveEventsHook(
        self,
        funcs: Union[
            Callable[[Any], Any],
            Iterable[Callable[[Any], Any]]]
        ) -> None:
        
        """Removes function(s) as event hooks.
            Note that this is without consideration for the type of hook.

        Args:
            funcs (Union[ Callable[[Any], Any], Iterable[Callable[[Any], Any]]]):
                callable or iterable of callable.
        """
        if callable(funcs):
            for hooktype in self.ALLHOOKS:
                if funcs in hooktype:
                    hooktype.remove(funcs)
        elif hasattr(funcs, '__iter__'):
            for hook_function in funcs:
                self.RemoveEventsHook(hook_function)


    def _callTileHooks(self, tile: str) -> None:
        self.ground = tile
        for func in self._tileEventHooks:
            func(self, tile)

    def _callAccelerometerHooks(self, x: int, y: int, z: int) -> None:
        self.acceleration = (x, y, z)
        for func in self._accelerometerEventHooks:
            func(self, x, y, z)
    
    def _callPantsHooks(self, powerup: str) -> None:
        self.pants = powerup
        for func in self._pantsEventHooks:
            func(self, powerup)

    def _handle_events(self, sender: int, data: bytearray) -> None:
        """Handles bluetooth notifications.
        
        Decodes the sent data and calls Mario's appropriate event hooks.

        Args:
            sender (int): Only necessary for bleak compatibility 
            data (bytearray): The data of the notification
        """
        hex_data = data.hex()
        # Port Value
        if data[2] == 0x45:
            # Camera Sensor Data
            if data[3] == 0x01:
                if data[5] == data[6] == 0xff:
                    self._log("IDLE?, Hex: %s" % hex_data)
                    return
                # RGB code
                if data[5] == 0x00:
                    tile = HEX_TO_RGB_TILE.get(
                        data[4], 
                        f"Unkown Tile Code: {hex(data[4])}")
                    self.recentTile = tile
                    self._log("%s Tile, Hex: %s" % (tile, hex_data))
                    self._callTileHooks(tile)
                # Ground Colors
                elif data[5] == 0xff:
                    color = HEX_TO_COLOR_TILE.get(
                        data[6],
                        f"Unkown Color: {hex(data[6])}")
                    self._log(f"{color} Ground, Hex: {hex_data}")
                    self._callTileHooks(color)

            # Accelerometer data
            elif data[3] == 0x00:
                # Gesture Mode - experimental, likely not accurate
                if data[4:6] == data[6:]:
                    gesture = ""
                    integer_data = int.from_bytes(data[4:6], "big")
                    for bin_gest in BINARY_GESTURES.keys():
                        if integer_data & bin_gest:
                            gesture += BINARY_GESTURES[bin_gest]
                    self._log(gesture)

                # RAW Mode
                else:
                    x = int(signed(data[4]))
                    y = int(signed(data[5]))
                    z = int(signed(data[6]))
                    self._log("X: %i Y: %i Z: %i" % (x, y, z), end="")
                    self._callAccelerometerHooks(x, y, z)

            # Pants data
            elif data[3] == 0x02:
                pants = HEX_TO_PANTS.get(data[4], "Unkown")
                binary_pants = bin(data[4])
                self._log(f"{pants} Pants, "
                    f"Pants-Only Binary: {binary_pants}," 
                    f"Hex: {hex_data}")
                self._callPantsHooks(pants)
            # Port 3 data - uncertain about all of it
            elif data[3] == 0x03:
                if data[4] == 0x13 and data[5] == 0x01:
                    tile = HEX_TO_RGB_TILE.get(data[6], "Unkown Tile")
                    self._log(f"Port 3: Jumped on {tile}, Hex: {hex_data}")
                else:
                    #TBD
                    self._log(
                        f"Unknown value from port 3: {data[4:].hex()}, "
                        f"Hex: {hex_data}")
            else:
                self._log(
                    f"Unknown value from port {data[3]}: "
                    f"{data[4:].hex()}, Hex: {hex_data}")

        # other technical messages
        elif data[2] == 0x02: # Hub Actions
            action = HEX_TO_HUB_ACTIONS.get(
                data[3], 
                f"Unkown Hub Action, Hex: {hex_data}")
            self._log(f"{action}, Hex: {hex_data}")
            if data[3] == 0x31: # 0x31 = Hub Will Disconnect
                asyncio.get_event_loop().create_task(self.disconnect())
        elif data[2] == 0x04: # Hub Attached I/O
            if data[4]:
                self._log(f"Port {data[3]} got attached, Hex: {hex_data}")
            else:
                self._log(
                    f"Port {data[3]} got detached, "
                    f"this shouldn't happen. Hex: {hex_data}")
        elif data[2] == 0x47: # Port Input Format Handshake
            self._log(
                f"Port {data[3]} changed to mode {data[4]} "
                f"with{'out' if not data[9] else ''} notifications, "
                f"Hex: {hex_data}")
        elif data[2] == 0x01 and data[4] == 0x06:
            property = HEX_TO_HUB_PROPERTIES.get(data[3], "Unknown Property")
            self._log(
                f"Hub Update About {property}: "
                f"{data[5:].hex()}, "
                f"Hex: {hex_data}")
        else:   # Other
            self._log(
                f"Unknown message - check Lego Wireless Protocol, "
                f"Hex: {hex_data}")

    async def connect(self) -> bool:
        self._run = True
        retries=0
        while self._run:
            retries+=1
            if retries > 3:
                self._log("Stopped after 3 attempts, disconnecting...")
                break
            self._log("Searching for device...")
            devices = await BleakScanner.discover()
            for d in devices:
                if d.name and (
                    d.name.lower().startswith("lego luigi") 
                    or 
                    d.name.lower().startswith("lego mario")
                    ):
                    try:
                        client = BleakClient(d.address)
                        await client.connect()
                        self._client = client
                        self._log(f"Mario Connected: {client.address}")

                        # subscribe to events
                        await client.start_notify(
                            LEGO_CHARACTERISTIC_UUID, 
                            self._handle_events)
                        await asyncio.sleep(0.1)
                        await client.write_gatt_char(
                            LEGO_CHARACTERISTIC_UUID, 
                            SUBSCRIBE_IMU_COMMAND)
                        await asyncio.sleep(0.1)
                        await client.write_gatt_char(
                            LEGO_CHARACTERISTIC_UUID, 
                            SUBSCRIBE_RGB_COMMAND)
                        await asyncio.sleep(0.1)
                        await client.write_gatt_char(
                            LEGO_CHARACTERISTIC_UUID, 
                            SUBSCRIBE_PANTS_COMMAND)

                        client.is_connected # wait for connection

                        asyncio.get_event_loop().create_task(
                            self.check_connection_loop())
                        
                        # change volume to provided default
                        if not self.defaultVolume is None: 
                            self.set_volume(self.defaultVolume)
                        return True
                    except: # any error during communication
                        self._log("Error connecting")
                        await self.disconnect()
                        return False
        await self.disconnect()
        return False

    async def request_port_value(self, port:int=0) -> None:
        """Method for sending request for color sensor port value to Mario.
        Default port is 0.
        0 - Accelerometer
        1 - Camera
        2 - Pants
        3 - unknown
        4 - unknown
        6 - voltage?
        Response will be sent to event handlers.

        Args:
            port (int, optional): Port to request value from. Defaults to 0.
        """
        assert port in (0,1,2,3,4,6), "Use a supported port (0,1,2,3,4,6)"
        if self._client:
            try:
                command = REQUEST_RGB_COMMAND
                command[3] = port
                command = bytearray(command)
                await self._client.write_gatt_char(LEGO_CHARACTERISTIC_UUID,
                                                    command)
            except (OSError, BleakError):
                self._log("Connection error while requesting port value")
                await self.disconnect()

    def set_volume(self, new_volume: int) -> None:
        """Sets mario's volume to the specified volume.

        Args:
            new_volume (int): Percentage of maximum volume. 
                Values <0 or >100 will be set to 0 or 100 respectively.
        """
        new_volume = min(max(new_volume, 0), 100)
        if self._client:
            try:
                command = bytearray([*MUTE_COMMAND[:5], new_volume])
                asyncio.get_event_loop().create_task(
                    self._client.write_gatt_char(
                        LEGO_CHARACTERISTIC_UUID, 
                        command)
                    )
            except (OSError, BleakError):
                self._log("Connection error while setting volume")
                asyncio.get_event_loop().create_task(self.disconnect())

    def port_setup(self, port: int, mode: int, notifications: bool = True) -> None:
        """Configures the settings of one of Mario's ports.
        Sends a message to Mario that configures the way one of its ports communicates.

        Args:
        port (int): The designated Port.
            Port 0: Accelerometer
            Port 1: Camera
            Port 2: Binary (Pants)
            Port 3: ??
            Port 4: ??
        mode (int): The mode to set the port to. 
            Available modes: 
                Port 0: (0,1), 
                Port 1: (0,1), 
                Port 2: (0), 
                Port 3: (0,1,2,3), 
                Port 4: (0,1).
            Also see https://github.com/bricklife/LEGO-Mario-Reveng
        notifications (bool, optional): Whether to receive updates about 
            new values of the port. Defaults to True. 
            If False, you'll need to manually request port values.
        """
        if self._client:
            try:
                command = pifs_command(port, mode, notifications)
                asyncio.get_event_loop().create_task(self._client.write_gatt_char(LEGO_CHARACTERISTIC_UUID, command))
            except (OSError, BleakError):
                self._log("Connection error while setting up port")
                asyncio.get_event_loop().create_task(self.disconnect())

    async def check_connection_loop(self) -> None:
        while self._client:
            try:
                if not self._client.is_connected:
                    self._log("Disconnect detected during connection check")
                    await self.disconnect()
                await asyncio.sleep(3)
            except (OSError, BleakError):
                self._log("Error during connection check")
                await self.disconnect()

    async def disconnect(self) -> None:
        try:
            self._log("Disconnecting... ")
            if self._client:
                await self._client.write_gatt_char(LEGO_CHARACTERISTIC_UUID, DISCONNECT_COMMAND)
                await self._client.disconnect()
                self._client = None
        except (OSError, BleakError):
            self._log("Connection error while disconnecting")
            self._client = None
        if self._autoReconnect:
            asyncio.get_event_loop().create_task(self.connect())
        else:
            self._run = False

    async def turn_off(self) -> None:
        try:
            self._log("Turning Off... ")
            await self._client.write_gatt_char(LEGO_CHARACTERISTIC_UUID, TURN_OFF_COMMAND)
            await self.disconnect()
        except (OSError, BleakError):
                self._log("Connection error while turning off")
                await self.disconnect()

def signed(char):
        return char - 256 if char > 127 else char

def run():
    while asyncio.all_tasks(loop=asyncio.get_event_loop()):
        asyncio.get_event_loop().run_until_complete(asyncio.gather(*asyncio.all_tasks(loop=asyncio.get_event_loop())))