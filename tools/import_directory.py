"""Import public coordinates from a saved official Prague tourism cinema directory.

Usage: python tools/import_directory.py /path/to/saved-directory.html
Prints a patch for review; does not download or modify the registry.
"""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from moviecache import Tree

NAMES={'Kino Aero':'kino-aero','Atlas Cinema':'kino-atlas','Bio Oko':'bio-oko',
       'Cinema City & IMAX® Flora':'cinema-city-flora','CineStar Praha — Anděl':'cinestar-andel',
       'CineStar Praha — Černý Most':'cinestar-cerny-most','Dlabačov Cinema':'dlabacov',
       'Edison Filmhub':'edison-filmhub','Evald Cinema':'kino-evald','Kino 35':'kino-35',
       'Kino Kavalírka cinema':'kino-kavalirka','Kino MAT':'kino-mat','Kino Pilotů cinema':'kino-pilotu',
       'Lucerna Cinema':'kino-lucerna','Modřany Cinema':'modransky-biograf','Ponrepo Cinema':'ponrepo',
       'Přítomnost Boutique Cinema':'kino-pritomnost','Radotín cinema':'kino-radotin','Světozor Cinema':'kino-svetozor'}
if __name__=='__main__':
    r=Tree(Path(sys.argv[1]).read_text()).root
    points=json.loads(r.all(lambda n:'data-mapdata' in n.attrs)[0].attrs['data-mapdata'])
    cards={n.attrs['data-poid']:n for n in r.all(lambda n:'data-poid' in n.attrs)}
    old=Path('venues.json').read_text();venues=json.loads(old)
    for p in points:
        card=cards.get(str(p['poid']));head=card.all(lambda n:n.tag=='h2') if card else []
        name=head[0].text().strip() if head else ''
        v=next((v for v in venues if v['id']==NAMES.get(name)),None)
        if not v:continue
        v.update(coordinates=[round(p['lng'],7),round(p['lat'],7)],coordinates_verified_at='2026-10-24',
                 coordinates_source='https://prague.eu/en/objevujte-kategorie/cinemas/')
        if v['address'] is None and not p['address'][0].isdigit():v['address']=p['address']
    new=json.dumps(venues,ensure_ascii=False,indent=2)+'\n'
    print('*** Begin Patch\n*** Update File: venues.json\n@@\n'+''.join('-'+x+'\n' for x in old.splitlines())+''.join('+'+x+'\n' for x in new.splitlines())+'*** End Patch')
