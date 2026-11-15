import {useEffect, useMemo, useRef, useState} from 'react';
import {flushSync} from 'react-dom';
import {matches, parseCatalogue, parseHost} from './catalog';
import {publicAsset} from './paths';
import {petHref, readSelection, resolveSelection} from './selection.mjs';
import type {PetSelection} from './selection.mjs';
import type {Catalogue, HostConfig, Pet, RoleFilter} from './types';
import {CompanyList} from './components/CompanyList';
import {PetDetail} from './components/PetDetail';
import {QrDialog} from './components/QrDialog';
import {registerCatalogTools} from './webmcp';

type State = {catalogue: Catalogue; config: HostConfig} | null;

export default function App() {
  const [data, setData] = useState<State>(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [query, setQuery] = useState('');
  const [role, setRole] = useState<RoleFilter>('all');
  const [selection, setSelection] = useState<PetSelection>(() => readSelection(window.location.search));
  const [qrPet, setQrPet] = useState<Pet | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setError('');
    const read = async (path: string) => {
      const response = await fetch(publicAsset(path), {signal: controller.signal});
      if (!response.ok) throw new Error('The companion collection could not be loaded. Please try again.');
      return response.json();
    };
    void Promise.all([read('catalog.json'), read('host-config.json')])
      .then(([catalogue, host]) => {
        if (!controller.signal.aborted) setData({catalogue: parseCatalogue(catalogue), config: parseHost(host)});
      })
      .catch(e => {
        if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'The collection could not be loaded.');
      });
    return () => controller.abort();
  }, [retry]);

  const filtered = useMemo(
    () => data?.catalogue.pets.filter(p => matches(p, query, role)) || [],
    [data, query, role],
  );
  const choice = data
    ? resolveSelection(data.catalogue.pets, filtered, selection)
    : {pet: null, reason: null};
  const selected = choice.pet;
  const selectedSlug = useRef<string | null>(null);
  selectedSlug.current = selected?.slug ?? null;

  function select(pet: Pet) {
    const href = petHref(window.location.href, pet.slug);
    setSelection({kind: 'explicit', slug: pet.slug});
    setQrPet(null);
    if (href !== window.location.href) window.history.pushState(null, '', href);
  }

  useEffect(() => {
    if (!data) return;
    const registration = registerCatalogTools({
      document: document as Parameters<typeof registerCatalogTools>[0]['document'],
      catalogue: data.catalogue,
      getSelectedSlug: () => selectedSlug.current,
      async selectCompanion(slug) {
        const pet = data.catalogue.pets.find(candidate => candidate.slug === slug);
        if (!pet) throw new Error('companion_not_found');
        flushSync(() => {
          setQuery('');
          setRole('all');
          select(pet);
        });
        await new Promise<void>(resolve => window.requestAnimationFrame(() => resolve()));
        document.getElementById('pet-title')?.focus({preventScroll: true});
      },
      onError: () => console.warn('Catalog agent tools could not be registered.'),
    });
    return () => registration.dispose();
  }, [data]);

  useEffect(() => {
    const onHistory = () => {
      setSelection(readSelection(window.location.search));
      setQrPet(null);
      setQuery('');
      setRole('all');
    };
    window.addEventListener('popstate', onHistory);
    return () => window.removeEventListener('popstate', onHistory);
  }, []);

  const missing = choice.reason === 'invalid' || choice.reason === 'unknown';
  const hidden = choice.reason === 'filtered';

  return (
    <>
      <a className="skip-link" href="#collection-main">Skip to companions</a>
      <div className="page-shell">
        <header className="site-header">
          <a className="wordmark" href={data ? `${data.config.canonicalOrigin}/studio` : '#collection-main'} aria-label="Chibi home">chibi.pet</a>
          <nav aria-label="Main navigation">
            <a href="#collection-main" aria-current="page">Junction</a>
            <a href={publicAsset('apps/knowledge-os/index.html')}>Knowledge OS</a>
            {data && <a href={`${data.config.canonicalOrigin}/${data.config.locale}/den`}>My Chibi</a>}
          </nav>
        </header>
        <main id="collection-main">
          <div className="collection-heading">
            <h1>Junction companions</h1>
            <p>Meet the companies. Find your companion.</p>
          </div>
          {error ? (
            <section className="load-state" role="alert">
              <h2>Let's try that again</h2>
              <p>{error}</p>
              <button type="button" className="button button-primary" onClick={() => setRetry(v => v + 1)}>Retry</button>
            </section>
          ) : !data ? (
            <div className="load-state" role="status">Opening the companion collection…</div>
          ) : (
            <div className="catalogue-layout">
              <CompanyList
                all={data.catalogue.pets}
                filtered={filtered}
                query={query}
                onQuery={setQuery}
                role={role}
                onRole={setRole}
                selected={selected}
                onSelect={select}
              />
              {selected ? (
                <PetDetail key={selected.id} pet={selected} config={data.config} onQr={() => setQrPet(selected)}/>
              ) : (
                <section className="detail-empty" role="status">
                  <h2>{missing ? 'Companion link not found' : hidden ? 'Hidden by your filters' : 'A companion for your next idea.'}</h2>
                  <p>
                    {missing
                      ? 'This link does not match an available company profile. Choose a company from the list.'
                      : hidden
                        ? 'Your selected companion is outside these search results. Clear the filters or choose another company.'
                        : 'Clear the search to explore the company collection.'}
                  </p>
                  {hidden && <button type="button" className="button button-secondary" onClick={() => {setQuery(''); setRole('all');}}>Clear filters</button>}
                </section>
              )}
            </div>
          )}
        </main>
        <footer className="site-footer">
          <span>Built by Chibi for conversations that go somewhere.</span>
          <span>Independent company companions</span>
        </footer>
      </div>
      {qrPet && data && <QrDialog pet={qrPet} config={data.config} onClose={() => setQrPet(null)}/>}
    </>
  );
}
