"""Solve jobs (spec P3-02): queue, worker process, progress stream.

A 10-minute column solve must not block an API worker: the API enqueues a
:class:`~ngdesign.jobs.models.Job`, a worker process claims it, solves through
``ngdesign.agent.engine.solve_project`` (the one solve path, spec B-08) while
streaming every P2-02 :class:`TearRecord` as progress, and persists the result
as a store ``SolveRow`` (spec P3-01).

Backends: :class:`~ngdesign.jobs.queue.LocalQueue` (thread-backed, same
process, the default and what every test uses) and
:class:`~ngdesign.jobs.queue.RedisQueue` (``STOMATO_REDIS_URL``) for the
multi-replica deployment. Subpackage layout: ``models`` (the Job record),
``queue`` (the JobQueue protocol and both backends), ``worker`` (the run
loop). Layer placement: between ``ngdesign.api`` and ``ngdesign.store`` — the
API and the CLI import jobs; jobs imports the store, agent, solver and
contracts.
"""
