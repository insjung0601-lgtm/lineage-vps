package l1j.server.telnet.command;

import static l1j.server.telnet.command.TelnetCommandResult.*;

import java.text.SimpleDateFormat;
import java.util.Calendar;

import l1j.server.server.TimeController.WarTimeController;
import l1j.server.server.datatables.CastleTable;
import l1j.server.server.datatables.ClanTable;
import l1j.server.server.model.L1Clan;
import l1j.server.server.model.L1World;
import l1j.server.server.model.Instance.L1PcInstance;
import l1j.server.server.serverpackets.S_CastleMaster;
import l1j.server.server.templates.L1Castle;

/* solo web manager: siege control (127.0.0.1 only) */

final class SoloSiege {
    static L1Castle castle(String arg) {
        try {
            return CastleTable.getInstance().getCastleTable(Integer.parseInt(arg.trim()));
        } catch (Exception e) {
            return null;
        }
    }

    static L1Clan owner(int castleId) {
        for (L1Clan c : L1World.getInstance().getAllClans()) {
            if (c.getCastleId() == castleId) return c;
        }
        return null;
    }

    static void crownIcon(L1Clan clan, int castleId) {
        if (clan == null) return;
        L1PcInstance leader = L1World.getInstance().getPlayer(clan.getLeaderName());
        if (leader != null) {
            leader.sendPackets(new S_CastleMaster(castleId, leader.getId()));
            L1World.getInstance().broadcastPacketToAll(new S_CastleMaster(castleId, leader.getId()));
        }
    }
}

/** castles -> id \t name \t ownerClan \t ownerLeader \t warStart \t nowWar */
class SoloCastlesCommand implements TelnetCommand {
    public TelnetCommandResult execute(String args) {
        SimpleDateFormat f = new SimpleDateFormat("yyyy-MM-dd HH:mm");
        StringBuilder sb = new StringBuilder();
        for (L1Castle c : CastleTable.getInstance().getCastleTableList()) {
            if (c == null) continue;
            L1Clan o = SoloSiege.owner(c.getId());
            boolean war = false;
            try { war = WarTimeController.getInstance().isNowWar(c.getId()); } catch (Exception e) { }
            sb.append(c.getId()).append('\t').append(c.getName()).append('\t')
              .append(o == null ? "" : o.getClanName()).append('\t')
              .append(o == null ? "" : o.getLeaderName()).append('\t')
              .append(c.getWarTime() == null ? "" : f.format(c.getWarTime().getTime())).append('\t')
              .append(war ? 1 : 0).append("\r\n");
        }
        return new TelnetCommandResult(CMD_OK, sb.toString());
    }
}

/** clans -> name \t leader \t castleId */
class SoloClansCommand implements TelnetCommand {
    public TelnetCommandResult execute(String args) {
        StringBuilder sb = new StringBuilder();
        for (L1Clan c : L1World.getInstance().getAllClans()) {
            sb.append(c.getClanName()).append('\t').append(c.getLeaderName()).append('\t')
              .append(c.getCastleId()).append("\r\n");
        }
        return new TelnetCommandResult(CMD_OK, sb.toString());
    }
}

/** warstart <castleId> <minutesFromNow> */
class SoloWarStartCommand implements TelnetCommand {
    public TelnetCommandResult execute(String args) {
        String[] a = args.trim().split("\\s+");
        if (a.length < 2) return new TelnetCommandResult(CMD_INTERNAL_ERROR, "usage: warstart <castleId> <minutes>");
        L1Castle c = SoloSiege.castle(a[0]);
        if (c == null) return new TelnetCommandResult(CMD_INTERNAL_ERROR, "no castle");
        int min;
        try { min = Integer.parseInt(a[1]); } catch (Exception e) { return new TelnetCommandResult(CMD_INTERNAL_ERROR, "bad minutes"); }
        if (WarTimeController.getInstance().isNowWar(c.getId())) return new TelnetCommandResult(CMD_INTERNAL_ERROR, "already at war");
        Calendar cal = Calendar.getInstance();
        cal.add(Calendar.MINUTE, Math.max(0, min));
        cal.add(Calendar.SECOND, -1);
        CastleTable.getInstance().updateWarTime(c.getName(), cal);
        WarTimeController.getInstance().setWarStartTime(c.getName(), cal);
        return new TelnetCommandResult(CMD_OK, new SimpleDateFormat("yyyy-MM-dd HH:mm").format(cal.getTime()));
    }
}

/** warstop <castleId> */
class SoloWarStopCommand implements TelnetCommand {
    public TelnetCommandResult execute(String args) {
        L1Castle c = SoloSiege.castle(args);
        if (c == null) return new TelnetCommandResult(CMD_INTERNAL_ERROR, "no castle");
        if (!WarTimeController.getInstance().isNowWar(c.getId())) return new TelnetCommandResult(CMD_INTERNAL_ERROR, "not at war");
        WarTimeController.getInstance().stopWar(c.getName());
        return new TelnetCommandResult(CMD_OK, "stopped");
    }
}

/** castleowner <castleId> <clanName | -> */
class SoloCastleOwnerCommand implements TelnetCommand {
    public TelnetCommandResult execute(String args) {
        String s = args.trim();
        int sp = s.indexOf(' ');
        if (sp < 0) return new TelnetCommandResult(CMD_INTERNAL_ERROR, "usage: castleowner <castleId> <clan|->");
        L1Castle c = SoloSiege.castle(s.substring(0, sp));
        if (c == null) return new TelnetCommandResult(CMD_INTERNAL_ERROR, "no castle");
        String clanName = s.substring(sp + 1).trim();
        L1Clan target = null;
        if (!clanName.equals("-")) {
            target = L1World.getInstance().getClan(clanName);
            if (target == null) return new TelnetCommandResult(CMD_INTERNAL_ERROR, "no clan");
        }
        L1Clan old = SoloSiege.owner(c.getId());
        if (old != null && old != target) {
            old.setCastleId(0);
            ClanTable.getInstance().updateClan(old);
            SoloSiege.crownIcon(old, 0);
        }
        if (target != null) {
            if (target.getCastleId() != 0 && target.getCastleId() != c.getId()) {
                return new TelnetCommandResult(CMD_INTERNAL_ERROR, "clan already owns another castle");
            }
            target.setCastleId(c.getId());
            ClanTable.getInstance().updateClan(target);
            SoloSiege.crownIcon(target, c.getId());
        }
        return new TelnetCommandResult(CMD_OK, "ok");
    }
}
