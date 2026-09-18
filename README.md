# JBL Synthesis for Home Assistant

Control a JBL Synthesis **SDR-35**, **SDR-38**, **SDP-55** or **SDP-58** from Home
Assistant over its IP control interface. These units are JBL's builds of the Arcam HDA
platform, and this integration drives them through a fork of the
[arcam-fmj](https://github.com/elupus/arcam_fmj) library carrying the JBL Synthesis
additions (model recognition, the Logic 16 Immersion decode mode, and General Setup /
Engineering Menu decoding) until they are merged upstream.

## What you get

| Entity | What it does |
| --- | --- |
| Media player | Power, volume (set and step), mute, input selection, and decode-mode selection — including Logic 16 Immersion, with the mode list tracking whether the incoming stream is stereo or multi-channel |
| Room EQ select | Which Dirac Live calibration slot is active, using the slot names stored on the receiver |
| Audio format sensor | The incoming stream as the front panel words it, e.g. `Dolby Atmos` or `DTS-HD Master Audio 3/4.1` |
| Input name sensor | The user-assigned name of the current input |
| Incoming video sensor | e.g. `3840x2160p60 (Dolby Vision)` |
| Sample rate, bitrate, dialogue normalisation | Stream diagnostics |
| Control connection switch | Releases the receiver's single control connection for other tools (see below) |

Diagnostics download and full unit-test coverage are included; the quality bar is
tracked rule-by-rule in
[`quality_scale.yaml`](custom_components/jblsynthesis/quality_scale.yaml).

## Requirements on the receiver

These are the settings JBL's own drivers for Control4, Crestron, RTI, ELAN and URC ask
installers to make.

- **General Setup → Control → IP.** The options are Off, RS232 and IP, and Off is the
  factory default. Holding the front-panel DIRECT button for four seconds turns on
  *RS232* control, not IP.
- **HDMI Settings → HDMI Bypass & IP → On**, if you want to power the unit on from Home
  Assistant. With it off, the receiver leaves the network entirely in standby: nothing
  can wake it over IP, and the integration shows its entities as unavailable until the
  unit is switched on another way.
- **Standby Mode → Manual**, in the unit's Engineering menu. JBL's RTI driver notes that
  with Standby Mode on Auto the unit ignores control commands while it is in standby.
- **Firmware 1.42/09 or later.** Earlier firmware got several control commands wrong,
  and JBL's URC and ELAN drivers require at least this version.
- **A fixed address.** Give the receiver a static IP or a DHCP reservation. Its subnet
  mask is always 255.255.255.0, so Home Assistant needs to be on the same /24 network or
  reach it through a router.
- **No other controller while Home Assistant is connected.** The unit sends its
  feedback to whichever connection made the most recent request, and its own web page
  and the JBL app count as connections. See
  [Sharing the receiver with Dirac Live](#sharing-the-receiver-with-dirac-live).

## Installation

### HACS

1. HACS → Integrations → ⋮ → *Custom repositories*.
2. Add `https://github.com/reubenbijl/ha-jblsynthesis` as an *Integration*.
3. Install **JBL Synthesis**, then restart Home Assistant.

### Manual

Copy `custom_components/jblsynthesis` into your Home Assistant `config/custom_components`
directory and restart.

## Configuration

Settings → Devices & Services → *Add Integration* → **JBL Synthesis**.

| Field | Meaning |
| --- | --- |
| Host | The receiver's hostname or IP address, shown on the unit under Network Settings |
| Port | The IP control port. The receiver always uses 50000, so change it only if you reach the unit through a port forward |

The receiver must be awake while you add it: the flow identifies the unit over the
control connection (make and model) before creating the entry. If the address later
changes, use *Reconfigure* on the entry rather than deleting it, so entities and
history are kept.

## How data flows

This is a push integration. One TCP connection stays open, and the receiver reports on
it every change made with its front panel or remote. Home Assistant polls nothing; the
library re-reads a little state on the same connection, paced the way JBL's own drivers
do it:

- every 5 seconds, what the receiver does not report by itself: the incoming stream
  (format, sample rate, video, input name) and the decode mode that goes with it;
- every 30 seconds, power, volume, mute and input, as a safety net, since the receiver
  can send its reports to another controller instead;
- every minute, everything else;
- everything at once after connecting, after the unit powers on (and again ten seconds
  later, once it has settled), and after an input change.

In standby only the power state is read. If the connection drops — deep standby, mains
off, network blip — the integration retries every ten seconds and logs once on the way
down and once on recovery.

## Replacing a Node-RED dashboard card

The media player replaces power/volume/input buttons one-for-one. A minimal example
mirroring a typical receiver card:

```yaml
type: vertical-stack
cards:
  - type: media-control
    entity: media_player.sdr_35
  - type: entities
    entities:
      - sensor.sdr_35_audio_format
      - sensor.sdr_35_input_name
      - sensor.sdr_35_incoming_video
      - select.sdr_35_room_eq
```

Scripted actions use the standard media player services, e.g. "volume to 45" is:

```yaml
action: media_player.volume_set
target:
  entity_id: media_player.sdr_35
data:
  volume_level: 0.4545   # 45 on the receiver's 0-99 scale
```

## Sharing the receiver with Dirac Live

The receiver services only a **small pool of control clients at a time — about two,
across raw TCP (50000) and websocket (50001) combined** (measured on an SDR-35).
Connections beyond the pool are not refused: TCP connects and even the websocket
handshake succeed, but requests are silently ignored, which makes the failure look
like anything except a connection limit. While this integration is connected it
permanently occupies one slot. Tools like the web client and Dirac Live appear to
use **two** connections each (one command channel, one live-values channel), which
means Dirac cannot run at all while this integration holds its slot — **turn the
Control connection switch off before every calibration session**, and treat a
stray open JBL app as another silent slot-holder.

Turn **Control connection** off to release the connection: every other entity goes
unavailable (the integration genuinely knows nothing while disconnected), the switch
itself stays available, and the port is free for Dirac Live. When you are done, turn it
back on: the integration reconnects and re-reads the full receiver state, so nothing
needs a manual refresh — including a Dirac calibration you just changed, since the
room-EQ slot names are re-fetched too.

The setting is not persisted: a Home Assistant restart reconnects. If you restart Home
Assistant mid-calibration, turn the switch off again before resuming.

## Known limitations

- **Deep standby is unreachable.** With *HDMI Bypass & IP* off, powering on from Home
  Assistant is impossible over IP; use IR or turn that setting on.
- **Zone 1 only** for now. The hardware supports a second zone; support is planned once
  the single-zone integration has soaked.
- The decode-mode list depends on the incoming stream, so a mode you can see on the
  remote may be absent until the stream type matches.

## Troubleshooting

- *Config flow says it cannot connect*: confirm the receiver is awake, General Setup →
  Control is set to IP, and port 50000 is right.
- *Everything shows unavailable*: the connection is down — almost always deep standby.
  The integration reconnects by itself when the receiver returns.
- *Turning the receiver on from Home Assistant does nothing*: check HDMI Bypass & IP is
  on and Standby Mode is Manual (see
  [Requirements on the receiver](#requirements-on-the-receiver)).
- *Command rejected errors*: the receiver answers commands it cannot currently apply
  (for example during setup-menu use) with an error; the message carries the
  receiver's answer code.

## Removal

Settings → Devices & Services → JBL Synthesis → ⋮ → *Delete*. Then remove the
repository from HACS (or delete `custom_components/jblsynthesis` if installed
manually).
