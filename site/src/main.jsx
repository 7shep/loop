import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ArrowUpRight, ArrowRight, ArrowDown, GithubLogo, Sun, Moon, Check, Copy, Folder, FileText, GitBranch, BookOpen, PencilLine, ShieldCheck, Stack, ArrowBendUpLeft } from '@phosphor-icons/react';
import '@fontsource-variable/geist';
import './styles.css';

const GITHUB = 'https://github.com/7shep/loop';
const stages = [
  { name: 'Plan', icon: GitBranch, title: 'Give every section a purpose.', text: 'The planner turns your requirements and rubric into a section plan. A reviewer checks that plan before research begins.', file: 'Approved section plan', note: 'Requirements → plan → review' },
  { name: 'Research', icon: BookOpen, title: 'Keep the evidence close.', text: 'The researcher evaluates your supplied source links and records which claims they support. The writer receives that traceable evidence.', file: 'Evidence with source references', note: 'Supplied sources → supported claims' },
  { name: 'Write', icon: PencilLine, title: 'Build the draft, section by section.', text: 'The writer follows the approved plan and evidence, then runs a humanizer pass that preserves claims, structure, and citation markers.', file: 'Section draft with citations', note: 'Approved plan + evidence → draft' },
  { name: 'Review', icon: ShieldCheck, title: 'A checkpoint before moving on.', text: 'Reviewers check each draft and route revisions back to the right role. The assembled document gets a final review before output.', file: 'Reviewed final document', note: 'Draft → feedback → revision → approval' },
];

function Brand() {
  return <a className="brand" href="#top" aria-label="Loop home"><span className="brand-mark" aria-hidden="true"><span /></span><span>LOOP</span></a>;
}

function Workflow() {
  const [active, setActive] = useState(0);
  const stage = stages[active];
  function navigate(event, index) {
    let next;
    if (event.key === 'ArrowRight') next = (index + 1) % stages.length;
    if (event.key === 'ArrowLeft') next = (index + stages.length - 1) % stages.length;
    if (event.key === 'Home') next = 0;
    if (event.key === 'End') next = stages.length - 1;
    if (next !== undefined) {
      event.preventDefault(); setActive(next);
      document.getElementById(`stage-${next}`).focus();
    }
  }
  return <section id="workflow" className="workflow section" aria-labelledby="workflow-heading">
    <div className="section-heading"><h2 id="workflow-heading">A process you can follow.</h2><p>Specialized roles. Clear handoffs. A review before the next move.</p></div>
    <div className="workflow-board">
      <div className="board-label"><GitBranch size={17} /> The Loop workflow <span>Explore each role</span></div>
      <div className="stage-tabs" role="tablist" aria-label="Workflow roles">{stages.map((item, index) => <button key={item.name} id={`stage-${index}`} role="tab" aria-selected={active === index} aria-controls="stage-panel" tabIndex={active === index ? 0 : -1} onKeyDown={event => navigate(event, index)} onClick={() => setActive(index)}><item.icon size={25} weight="light" /><span>{item.name}</span>{index < 3 && <ArrowRight className="stage-arrow" size={18} />}</button>)}</div>
      <div className="stage-detail" id="stage-panel" role="tabpanel" aria-labelledby={`stage-${active}`} tabIndex={0}>
        <div key={stage.name} className="stage-copy"><h3>{stage.title}</h3><p>{stage.text}</p></div>
        <div className="artifact"><FileText size={27} weight="light" /><div><span>What moves forward</span><strong>{stage.file}</strong></div><Check size={18} /></div>
      </div>
      <div className="review-path"><ArrowBendUpLeft size={17} /><span>Feedback loops back until the review passes.</span><span className="stage-note">{stage.note}</span></div>
    </div>
  </section>;
}

function GetStarted() {
  const command = 'git clone https://github.com/7shep/loop.git\ncd loop\npython -m pip install -e .';
  const [copyState, setCopyState] = useState('Copy commands');
  async function copy() {
    try { await navigator.clipboard.writeText(command); setCopyState('Copied!'); }
    catch { setCopyState('Select the commands to copy'); }
  }
  return <section id="start" className="start section" aria-labelledby="start-heading">
    <div><p className="eyebrow">Open source. Yours to explore.</p><h2 id="start-heading">Start your next loop.</h2><p>Clone the project, install the engine, and set up the Loop and humanizer skills. Bring your own assignment.</p><a className="text-link" href={`${GITHUB}#setup`}>Read the setup guide <ArrowUpRight size={18} /></a></div>
    <div className="install"><div className="install-header"><span>Install locally <span className="python">Python 3.11+</span></span><button onClick={copy} aria-label={copyState} title={copyState}>{copyState === 'Copied!' ? <Check size={18} /> : <Copy size={18} />}</button></div><pre><code>{command}</code></pre><div className="install-foot"><span>No Python runtime dependencies.</span><span role="status">{copyState !== 'Copy commands' ? copyState : ''}</span></div></div>
  </section>;
}

function App() {
  const [theme, setTheme] = useState(() => {
    try { const saved = localStorage.getItem('loop-theme'); if (saved === 'light' || saved === 'dark') return saved; } catch { /* System preference remains available when storage is blocked. */ }
    return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });
  function toggleTheme() {
    const next = theme === 'dark' ? 'light' : 'dark'; setTheme(next);
    try { localStorage.setItem('loop-theme', next); } catch { /* Theme still works for this visit. */ }
  }
  return <div className="app" data-theme={theme} id="top">
    <a className="skip-link" href="#main">Skip to content</a>
    <div className="shell">
      <header><Brand /><nav aria-label="Main navigation"><a href="#workflow">Workflow</a><a href="#folder">Folder anatomy</a><a href="#start">Get started</a></nav><div className="header-actions"><button className="theme-toggle" aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`} onClick={toggleTheme}>{theme === 'dark' ? <Sun size={20} /> : <Moon size={20} />}</button><a className="github-link" href={GITHUB}><GithubLogo size={19} weight="fill" /><span>GitHub</span><ArrowUpRight size={16} /></a></div></header>
      <main id="main">
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-copy"><p className="eyebrow">Assignment orchestration for Codex</p><h1 id="hero-title">Big assignment.<br /><span>Small, clear steps.</span></h1><p className="hero-description">Turn your assignment folder into a structured workflow for planning, research, writing, and review.</p><div className="hero-actions"><a className="button primary" href={GITHUB}>Explore on GitHub <ArrowUpRight size={19} /></a><a className="button secondary" href="#workflow">How it works <ArrowDown size={17} /></a></div></div>
          <div className="hero-graphic" aria-label="Loop connects your assignment to planning, research, writing, and review">
            <div className="orbit orbit-outer" /><div className="orbit orbit-inner" />
            <div className="orbit-core"><span className="brand-mark large" aria-hidden="true"><span /></span><span>One conversation.</span><strong>A whole workflow.</strong></div>
            <div className="orbit-node node-plan"><GitBranch size={21} /><span>Plan</span></div><div className="orbit-node node-research"><BookOpen size={21} /><span>Research</span></div><div className="orbit-node node-write"><PencilLine size={21} /><span>Write</span></div><div className="orbit-node node-review"><ShieldCheck size={21} /><span>Review</span></div>
            <span className="orbit-caption">Your assignment stays at the center.</span>
          </div>
        </section>
        <div className="intro-strip"><span>Made for the work<br /><strong>between prompt and final draft.</strong></span><p>Loop coordinates specialized agents in one visible Codex or ChatGPT Work conversation. Every handoff leaves something you can inspect.</p></div>
        <Workflow />
        <section id="folder" className="folder-section section" aria-labelledby="folder-heading">
          <div className="folder-copy"><h2 id="folder-heading">One folder.<br />The full picture.</h2><p>Your prompt, rubric, and sources give Loop its context. Plans, evidence, and drafts stay alongside the work.</p><div className="principle"><Stack size={21} /><div><h3>Local and inspectable</h3><p>State and artifacts live in your assignment workspace.</p></div></div><div className="principle"><ShieldCheck size={21} /><div><h3>Review is part of the process</h3><p>Section checks and a final review gate the output.</p></div></div><a className="text-link" href={`${GITHUB}#architecture`}>Explore the architecture <ArrowUpRight size={17} /></a></div>
          <div className="folder-map"><div className="folder-title"><Folder size={23} weight="duotone" /><strong>your-assignment/</strong></div><div className="file-row"><FileText size={18} /><code>assignment.md</code><span>The brief</span></div><div className="file-row"><Folder size={18} /><code>outline/</code><span>Requirements & rubric</span></div><div className="file-row"><Folder size={18} /><code>sources/</code><span>Links & past feedback</span></div><div className="file-row generated"><Folder size={18} /><code>.loop/</code><span>Plans, evidence & state</span></div><div className="file-row generated"><Folder size={18} /><code>output/</code><span>Your final document</span></div><div className="folder-note"><ArrowRight size={16} /> Inputs in. A traceable process. Reviewed output.</div></div>
        </section>
        <GetStarted />
      </main>
      <footer><Brand /><span>A little structure goes a long way.</span><div><a href={`${GITHUB}/blob/main/LICENSE`}>MIT License</a><a href={GITHUB}>Source code <ArrowUpRight size={15} /></a></div></footer>
    </div>
  </div>;
}

createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>);
