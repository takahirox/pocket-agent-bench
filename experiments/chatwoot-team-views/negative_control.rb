# Maintainer-controlled mutations of the reference, isolated to this Ruby process.
require 'rails_helper'

case ENV.fetch('TEAM_VIEW_CONTROL')
when 'join_visibility'
  CustomFilter.singleton_class.prepend(Module.new do
    def visible_to(viewer, current_account)
      membership = current_account.account_users.find_by(user_id: viewer.id)
      return none unless membership

      personal = where(team_id: nil, user_id: viewer.id)
      shared = joins(:team).where(teams: { account_id: current_account.id })
      shared = shared.joins(team: :team_members).where(team_members: { user_id: viewer.id }) unless membership.administrator?
      where(id: personal.select(:id)).or(where(id: shared.select(:id))).distinct
    end
  end)
when 'reader_can_manage'
  CustomFilter.prepend(Module.new do
    def manageable_by?(_viewer) = true
  end)
when 'creator_deletes_shared'
  User.prepend(Module.new do
    def retain_team_views; end
  end)
when 'creator_unread_counts'
  Conversations::UnreadCounts::SharedFolderCounter.prepend(Module.new do
    def perform
      creator_id = @account.custom_filters.where.not(team_id: nil).pick(:user_id)
      @user = @account.users.find(creator_id) if creator_id
      super
    end
  end)
when 'stale_membership'
  CustomFilter.singleton_class.prepend(Module.new do
    def visible_to(viewer, current_account)
      @control_visible_ids ||= {}
      ids = @control_visible_ids[[viewer.id, current_account.id]] ||= super.pluck(:id)
      where(id: ids)
    end
  end)
else
  raise 'Unknown negative control'
end
