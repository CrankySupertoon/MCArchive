from flask import Blueprint, render_template, jsonify, request, url_for, redirect, flash, \
        abort, current_app as app

from mcarch.model.mod import Mod, ModAuthor, ModVersion, GameVersion
from mcarch.model.mod.draft import DraftMod
from mcarch.model.mod.logs import LogMod, gen_diffs
from mcarch.model.user import roles
from mcarch.login import login_required, cur_user, has_role
from mcarch.util.minecraft import key_mc_version
from mcarch.util.cache import unless_cur_user
from mcarch.app import db, cache

modbp = Blueprint('mods', __name__, template_folder="templates")

@modbp.route("/mods")
@cache.cached(query_string=True, unless=unless_cur_user)
def browse():
    by_author = request.args.get('author')
    by_gvsn = request.args.get('gvsn')
    keyword = request.args.get('kw')
    
    filters = {}
    if by_author:
        filters['author'] = by_author
    if by_gvsn:
        filters['game_vsn'] = by_gvsn
    if keyword:
        filters['keyword'] = keyword
    # list of filters to be listed on the page

    mods = Mod.search_query(**filters).all()
    return render_template("mods/browse.html", mods=mods, filters=filters, gvsn=by_gvsn)

@modbp.route("/mods/<slug>")
@cache.cached(query_string=True, unless=unless_cur_user)
def mod_page(slug):
    mod = Mod.query.filter_by(slug=slug).first_or_404()

    if not mod.redist and not has_role(roles.archivist):
        return abort(404)

    vsns = mod.vsns_by_game_vsn()
    by_gvsn = request.args.get('gvsn')
    if by_gvsn:
        vsns = { by_gvsn: vsns.get(by_gvsn) }

    return render_template("mods/mod.html", mod=mod, vsns_grouped=vsns, by_gvsn=by_gvsn)


@modbp.route("/authors")
def authors():
    authors = ModAuthor.query.all()
    return render_template('mods/authors.html', authors=authors)

@modbp.route("/gamevsns")
def gamevsns():
    gamevsns = sorted(GameVersion.query.all(), key=lambda a: key_mc_version(a.name), reverse=True)
    return render_template('mods/gamevsns.html', gamevsns=gamevsns)


@modbp.route("/mods/<slug>/history")
@login_required(role=roles.archivist)
def mod_history(slug):
    mod = Mod.query.filter_by(slug=slug).first_or_404()
    changes = gen_diffs(mod)
    return render_template("mods/history.html", mod=mod, changes=changes)

@modbp.route("/mods/<slug>/history/<index>")
@login_required(role=roles.archivist)
def mod_revision(slug, index):
    mod = Mod.query.filter_by(slug=slug).first_or_404()
    rev = LogMod.query.filter_by(cur_id=mod.id, index=index).first_or_404()
    vsns = rev.vsns_by_game_vsn()
    return render_template("mods/mod.html", mod=rev, rev=rev, vsns_grouped=vsns)

@modbp.route("/mods/<slug>/history/<index>/revert", methods=['GET', 'POST'])
@login_required(role=roles.moderator, pass_user=True)
def revert_mod(user, slug, index):
    mod = Mod.query.filter_by(slug=slug).first_or_404()
    revto = LogMod.query.filter_by(index=index, cur_id=mod.id).first_or_404()
    if request.method == 'POST':
        mod.revert_to(revto)
        db.session.commit()
        mod.log_change(user=user)
        db.session.commit()
        flash('Mod reverted to revision {}'.format(index))
        return redirect(url_for('mods.mod_page', slug=slug))
    else:
        diff = mod.diff(revto)
        return render_template("mods/revert_confirm.html", mod=mod, revto=revto, diff=diff)

