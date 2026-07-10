import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const priorities = [
  ['Cash flow review', 'High', 'Active'],
  ['TEN Leasing follow-up', 'High', 'Waiting'],
  ['CTPAT document preparation', 'Medium', 'Active'],
  ['IRS EIN follow-up', 'High', 'Waiting'],
  ['In-bond closure review', 'Medium', 'Active'],
];

const waiting = [
  ['IRS EIN update', 'IRS', 'Today'],
  ['TEN Leasing account setup', 'Monish', 'Today'],
  ['CTPAT document request', 'Compliance company', 'This week'],
];

function Card({title, children}) {
  return <section className="card"><h2>{title}</h2>{children}</section>;
}

function App() {
  const [company, setCompany] = useState(null);

useEffect(() => {
    fetch("http://127.0.0.1:8000/company")
        .then(res => res.json())
        .then(data => setCompany(data))
        .catch(console.error);
}, []);
  return (
    <main className="page">
      <header className="hero">
        <p>Polaris Chief of Staff v0.1</p>
        <h1>
Good Morning, {company ? company.company_name : "Founder"}
</h1>
        <h3>What requires your attention today?</h3>
      </header>
      <div className="grid">
        <Card title="Today's Priorities">
          {priorities.map(([t,p,s]) => <div className="row" key={t}><span>{t}</span><b>{p}</b><em>{s}</em></div>)}
        </Card>
        <Card title="Waiting On">
          {waiting.map(([i,c,f]) => <div className="row" key={i}><span>{i}</span><b>{c}</b><em>{f}</em></div>)}
        </Card>
        <Card title="Compliance"><p>GST • IFTA • KYU • CTPAT</p><small>Next: build deadline tracker.</small></Card>
        <Card title="Cash Position"><p>Manual input required</p><small>Next: connect QBO export.</small></Card>
        <Card title="Meetings"><p>Meeting intelligence pending</p><small>Preparation + action items.</small></Card>
        <Card title="Builder Journal"><p>Created first PCS dashboard scaffold.</p></Card>
      </div>
    </main>
  );
}

createRoot(document.getElementById('root')).render(<App />);
