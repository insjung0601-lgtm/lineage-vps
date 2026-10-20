/*
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2, or (at your option)
 * any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA
 * 02111-1307, USA.
 *
 * http://www.gnu.org/copyleft/gpl.html
 */
package l1j.server.telnet.command;

import javolution.util.FastMap;
import java.util.Map;

public class TelnetCommandList {
	private static Map<String, TelnetCommand> _cmds = new FastMap<String, TelnetCommand>();
	static {
		_cmds.put("echo", new EchoCommand());
		_cmds.put("playerid", new PlayerIdCommand());
		_cmds.put("charstatus", new CharStatusCommand());
		_cmds.put("globalchat", new GlobalChatCommand());
		_cmds.put("shutdown", new ShutDownCommand());
		_cmds.put("online", new SoloOnlineCommand());
		_cmds.put("gm", new SoloGmCommand());
		_cmds.put("save", new SoloSaveCommand());
		_cmds.put("kick", new SoloKickCommand());
		_cmds.put("notice", new SoloNoticeCommand());
		_cmds.put("castles", new SoloCastlesCommand());
		_cmds.put("clans", new SoloClansCommand());
		_cmds.put("warstart", new SoloWarStartCommand());
		_cmds.put("warstop", new SoloWarStopCommand());
		_cmds.put("castleowner", new SoloCastleOwnerCommand());
	}

	public static TelnetCommand get(String name) {
		return _cmds.get(name.toLowerCase());
	}
}
