"""Seed the blog with launch articles. Idempotent — skips slugs that exist."""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.blog.models import Post
from apps.catalog.models import Country

ARTICLES = [
    {
        "slug": "esim-vs-roaming-what-it-actually-costs",
        "title": "eSIM vs roaming: what a week abroad actually costs",
        "excerpt": "Roaming is priced per day whether you use it or not. A travel eSIM is priced per "
                   "gigabyte. Here is the arithmetic on a normal one-week trip.",
        "body": """
<p>Almost every operator now sells a "use your plan abroad" day pass. It is convenient and it is
expensive, because you pay the daily fee on the day you land, on the day you leave, and on every day
in between — including the ones where you only opened a map twice.</p>

<h2>The two pricing models</h2>
<p><strong>Roaming day passes</strong> charge a flat fee per calendar day of use, commonly between
$5 and $12 depending on the operator and destination. A seven-day trip is therefore $35 to $84
before you have used a single gigabyte.</p>
<p><strong>Travel eSIMs</strong> charge for a data bucket with a validity window. You buy 5 GB valid
for 15 days, and the price is the price no matter how many of those days you actually browse.</p>

<h2>A worked example</h2>
<p>Take a week in Italy for someone who uses maps, messaging, a bit of social and the occasional
video call. That is realistically 3–5 GB.</p>
<ul>
  <li><strong>Roaming day pass at $8/day:</strong> $56 for seven days.</li>
  <li><strong>Travel eSIM, 5 GB for 15 days:</strong> a few dollars, and the leftover days cover a
      weekend extension if your plans change.</li>
</ul>
<p>The gap is not marginal. It is usually an order of magnitude, and it grows with trip length,
because the eSIM price is flat while the roaming fee keeps ticking.</p>

<h2>When roaming still wins</h2>
<p>Two cases. First, if you need to receive calls and SMS on your own number at local rates —
travel eSIMs are data-only. Second, if your trip is a single overnight and your operator includes a
few roaming days free. Otherwise the eSIM is cheaper every time.</p>

<h2>How to compare honestly</h2>
<p>Ignore the headline price and work out the cost per gigabyte, then check the validity window. A
"cheap" 1 GB plan valid for 3 days is not cheap if you need 10 days of coverage. Every plan page on
this site shows both numbers, precisely so you do not have to do this in your head at the airport.</p>
""",
    },
    {
        "slug": "how-much-data-do-i-need-abroad",
        "title": "How much data do you actually need abroad?",
        "excerpt": "Maps, messaging and boarding passes use less than people fear. Video and hotspot "
                   "use far more. A realistic table plus the settings that stop silent drain.",
        "body": """
<p>The honest answer is that most travellers overbuy. Here is what the common activities consume so
you can size a plan without guessing.</p>

<h2>What each activity costs</h2>
<ul>
  <li><strong>Maps and navigation:</strong> roughly 5–10 MB per hour of active use. A full day of
      wandering a city rarely passes 100 MB.</li>
  <li><strong>Messaging (text, photos, voice notes):</strong> about 50–150 MB per day.</li>
  <li><strong>Social feeds with autoplay video:</strong> 100–300 MB per 30 minutes. This is where
      data disappears.</li>
  <li><strong>Video calls:</strong> around 300–500 MB per hour on standard quality.</li>
  <li><strong>Streaming video:</strong> 700 MB to 3 GB per hour depending on resolution.</li>
  <li><strong>Hotspot to a laptop:</strong> unpredictable, because desktop sites and background sync
      are much heavier than mobile apps. Assume at least double.</li>
</ul>

<h2>A sizing table that holds up</h2>
<ul>
  <li><strong>Weekend, light use:</strong> 1–3 GB.</li>
  <li><strong>One week, normal use:</strong> 5 GB.</li>
  <li><strong>Two weeks, normal use, some video:</strong> 10 GB.</li>
  <li><strong>A month, or you tether a laptop:</strong> 20 GB or an unlimited plan.</li>
  <li><strong>You stream daily or work from the road:</strong> unlimited, and stop counting.</li>
</ul>

<h2>Three settings that stop silent drain</h2>
<ol>
  <li>Turn off background app refresh on cellular. Photo backup is the single biggest hidden
      consumer on a trip full of photos.</li>
  <li>Disable autoplay video in your social apps. This alone often halves consumption.</li>
  <li>Download maps, playlists and shows over hotel Wi-Fi the night before, not on the road.</li>
</ol>

<h2>If you run out</h2>
<p>Top up. The data attaches to the same eSIM, so there is nothing to reinstall and no second QR code
to scan. That is why buying a slightly smaller plan first is the low-risk choice: running out is a
two-minute fix, while an unused 20 GB is money gone.</p>
""",
    },
    {
        "slug": "esim-not-working-checklist",
        "title": "eSIM installed but no internet? Work through this list",
        "excerpt": "Nine times out of ten it is one switch. The full diagnostic order, from the "
                   "setting everyone misses to the cases that need a replacement profile.",
        "body": """
<p>An eSIM that shows signal bars but carries no data is almost never a broken profile. Work down
this list in order and you will usually be online within a minute.</p>

<h2>1. Data roaming is off</h2>
<p>This is the fix in the large majority of cases, and it feels wrong, which is why people skip it. A
travel eSIM connects to <em>partner</em> networks at your destination, which technically counts as
roaming. With the setting off, the line registers, shows bars, and refuses to pass data.</p>
<p>On iPhone: Settings → Cellular → select the eSIM line → Data Roaming ON. On Android: Settings →
Network &amp; internet → SIMs → select the eSIM → Roaming ON.</p>

<h2>2. The eSIM is not the line used for data</h2>
<p>Two lines are active, so the phone needs telling which one carries data. Set the eSIM as the
mobile data line, and leave your home SIM as the default for calls and SMS so your own number keeps
working.</p>

<h2>3. It has not registered yet</h2>
<p>Toggle airplane mode on and off, wait thirty seconds, then restart the phone once. A freshly
installed profile often only registers properly on the next boot.</p>

<h2>4. The network was picked manually</h2>
<p>If automatic selection latched onto a partner with no coverage where you are standing, go to
network selection, switch to manual, and pick a different operator from the list. Then switch back to
automatic once you have a connection.</p>

<h2>5. The plan has not started or has run out</h2>
<p>Check the data counter in your account. A plan that expired or hit zero will connect and carry no
traffic. A top-up lands on the same eSIM and fixes it without reinstalling.</p>

<h2>6. The phone is carrier-locked</h2>
<p>A handset still locked to your home operator rejects every other network. There is no setting that
works around this — the operator has to unlock it, which is usually free once the device is paid off.</p>

<h2>7. An APN is required</h2>
<p>Rare, but some networks want it typed in. The APN for your plan is shown on your eSIM page in the
dashboard; enter it under the eSIM line's cellular data network settings.</p>

<h2>Still stuck?</h2>
<p>Send us the ICCID from your dashboard. We can see the line's own network log — whether it
registered, which operator it saw and when — so we are diagnosing the actual line rather than guessing
from a description.</p>
""",
    },
]


class Command(BaseCommand):
    help = "Create the launch blog articles (idempotent)."

    def handle(self, *args, **opts):
        created = 0
        for a in ARTICLES:
            if Post.objects.filter(slug=a["slug"]).exists():
                continue
            Post.objects.create(
                is_published=True, published_at=timezone.now(),
                seo_description=a["excerpt"][:300], **a,
            )
            created += 1
        # Link the roaming comparison to Italy so it cross-sells that destination.
        italy = Country.objects.filter(slug="italy").first()
        if italy:
            Post.objects.filter(slug="esim-vs-roaming-what-it-actually-costs").update(country=italy)
        self.stdout.write(self.style.SUCCESS(
            f"Blog: {created} new, {Post.objects.filter(is_published=True).count()} published"))
