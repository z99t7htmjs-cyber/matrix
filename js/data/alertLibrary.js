/**
 * Plain-language explanations for each kind of alert.
 *
 * Alerts carry a `kind` (e.g. "port-scan"); the details panel looks it up here
 * to show a "Learn more" section. Text wrapped in `backticks` is shown as code.
 * Kinds without an entry simply show no explainer.
 */
export const ALERT_LIBRARY = {
  'http-admin': {
    what: "The router's settings page is served over plain HTTP, so the username and password you type cross the network unencrypted.",
    why: 'Anything that can see your local traffic (a compromised device, or someone on your Wi-Fi) can capture the admin login. Whoever controls the router controls DNS, port forwarding and every device\'s route to the internet.',
    confirm: 'Open the router\'s admin address. If the browser says "Not secure" or the address starts with `http://`, logins are unencrypted.',
    fix: 'Enable HTTPS for the admin page, turn off remote (WAN) administration, and use a long, unique admin password.',
  },

  'firmware-outdated': {
    what: "Firmware is the router's operating system. Vendors release updates that patch security holes.",
    why: 'Router bugs are hunted by automated botnets (Mirai is the famous one) that scan the whole internet for unpatched devices. Routers are rarely updated, which makes them a favorite target.',
    confirm: 'Compare the firmware version on the admin page with the latest version on the vendor\'s support site.',
    fix: 'Install the update and turn on automatic updates if offered. A router that no longer receives updates (end-of-life) should be replaced.',
  },

  'smb-exposed': {
    what: 'SMB (Server Message Block) is Windows file and printer sharing. It listens on TCP port 445.',
    why: 'SMB has a history of serious bugs. The WannaCry ransomware (2017) spread between computers through an SMB flaw. Any infected device on your network could try the same.',
    confirm: 'In PowerShell, `Get-SmbShare` lists shared folders, and `netstat -an | findstr :445` shows whether port 445 is listening.',
    fix: "If you don't share files, turn off file and printer sharing (or set the network profile to Public). Keep Windows updated, and never forward port 445 on your router.",
  },

  'rdp-exposed': {
    what: 'Remote Desktop lets someone use this PC\'s screen, keyboard and mouse over the network. It listens on TCP port 3389.',
    why: 'Exposed Remote Desktop is one of the most common ways ransomware gangs get in, through password guessing or unpatched flaws such as BlueKeep (2019).',
    confirm: 'Settings → System → Remote Desktop shows whether it is on. `netstat -an | findstr :3389` shows whether the port is listening.',
    fix: "If you don't use it, turn it off. If you do, require Network Level Authentication, use a strong password, and never forward port 3389 on your router.",
  },

  'listening-ports': {
    what: 'These are the ports where this PC is waiting for other devices to connect. Each one belongs to a program or Windows service.',
    why: 'Every listening port is a door. The fewer doors, the smaller the "attack surface". Windows normally opens several (135, 139, 445 and a range above 49152 for internal services).',
    confirm: 'Run `netstat -ano | findstr LISTENING` in a command window. The last column is the process ID; match it in Task Manager\'s Details tab to see which program owns the port.',
    fix: 'Nothing is wrong by default. Look for ports you don\'t recognize, and uninstall or disable software you no longer use. Windows Firewall blocks most of these from outside your network.',
  },

  'device-unreachable': {
    what: 'The device stopped answering the periodic "are you there?" checks.',
    why: 'Usually harmless: it is off, asleep or out of range. It is worth a look when the silence is unexpected, or when a new device appears soon after using the same address.',
    confirm: 'Check whether the device is powered on and connected to Wi-Fi.',
    fix: 'Nothing to fix if the outage is expected.',
  },

  'new-device': {
    what: 'A device the network has never seen before got an IP address from the router (via DHCP).',
    why: "On most home networks every device can reach every other device. An unknown one might be a guest's phone, or someone who learned your Wi-Fi password, or a rogue gadget someone plugged in.",
    confirm: "Check the router's client list: the MAC address, the vendor (the first half of the MAC identifies the manufacturer), the hostname and when it joined. Phones and laptops often use randomized MACs, which have no vendor. Ask the people in your home.",
    fix: "If you can't explain it, block its MAC address on the router and change the Wi-Fi password. Putting guests and smart-home gadgets on a separate guest network limits what any one device can reach.",
  },

  'port-scan': {
    what: 'One device rapidly tried to connect to many ports on many other devices to learn which services are listening.',
    why: 'Scanning is reconnaissance, usually the first step of an attack: mapping what can be exploited. Ordinary phones, TVs and smart plugs almost never do it.',
    confirm: 'The telltale sign is one source touching many ports or hosts in a short time. Tools like Zeek or Suricata flag this automatically.',
    fix: "Isolate the scanning device, find out what it is, and turn off services you don't need so there is less to find.",
  },

  'brute-force': {
    what: 'Many login attempts in a row, each guessing a different password.',
    why: 'Default and weak passwords fall to automated guessing within seconds. A successful login to a router gives full control of the network.',
    confirm: "The router's system log lists failed logins and the address they came from.",
    fix: 'Use a long, unique admin password, enable lockout after failed attempts if available, allow admin access over HTTPS only, and block the source device.',
  },

  'suspicious-outbound': {
    what: 'A device opened a connection to an unfamiliar internet server on an unusual port. Port 4444 is the default for Metasploit, a popular attack framework.',
    why: 'This can be a "reverse shell" or command-and-control channel: the device calls out to an attacker, who then controls it. Routers usually block unsolicited inbound connections but allow outbound ones, so calling out is how attackers get around the firewall.',
    confirm: 'Look up the remote address on a reputation service such as AbuseIPDB or VirusTotal. On Windows, `netstat -b` (run as administrator) shows which program owns each connection.',
    fix: 'Disconnect the device, block the destination on the router, then investigate or wipe the device before reconnecting it.',
  },
};

const ALIASES = { 'device-offline': 'device-unreachable', 'unconfirmed-device': 'new-device' };

export function getAlertLesson(kind) {
  return ALERT_LIBRARY[kind] ?? ALERT_LIBRARY[ALIASES[kind]] ?? null;
}
